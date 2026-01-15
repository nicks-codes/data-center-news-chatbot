"""
News digest and story summary service for DC real estate audience.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import or_

from .chat_service import ChatService
from ..database.db import SessionLocal
from ..database.models import Article, Digest, StorySummary

logger = logging.getLogger(__name__)


class NewsDigestService:
    def __init__(self, chat_service: ChatService):
        self.chat_service = chat_service

    def get_or_create_digest(
        self,
        *,
        date_str: Optional[str],
        audience: Optional[str],
        window_days: int = 1,
    ) -> Dict[str, Any]:
        audience = (audience or "DC_RE").strip() or "DC_RE"
        date_obj = self._parse_date(date_str)
        date_key = date_obj.isoformat()
        window_days = self._clamp_days(window_days)

        db = SessionLocal()
        try:
            rows = (
                db.query(Digest)
                .filter(Digest.date == date_key, Digest.audience == audience)
                .order_by(Digest.id.desc())
                .all()
            )
            for row in rows:
                meta = self._parse_sources_json(row.sources_json)
                stored_days = int((meta or {}).get("window_days") or 1)
                if stored_days == window_days:
                    return {
                        "date": row.date,
                        "audience": row.audience,
                        "title": row.title,
                        "content_md": row.content_md,
                        "sources": (meta or {}).get("sources") or [],
                        "meta": meta or {},
                    }
        finally:
            db.close()

        generated = self.generate_digest(
            date_obj=date_obj,
            audience=audience,
            window_days=window_days,
        )

        db = SessionLocal()
        try:
            row = Digest(
                date=date_key,
                audience=audience,
                title=generated["title"],
                content_md=generated["content_md"],
                sources_json=json.dumps(generated.get("meta") or {}),
            )
            db.add(row)
            db.commit()
        finally:
            db.close()

        return generated

    def list_stories(
        self,
        *,
        days: int = 1,
        limit: int = 30,
        market: Optional[str] = None,
        topic: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        days = self._clamp_days(days)
        limit = max(1, min(int(limit or 30), 60))
        cutoff = datetime.utcnow() - timedelta(days=days)

        db = SessionLocal()
        try:
            q = db.query(Article).order_by(
                Article.published_date.desc().nullslast(),
                Article.scraped_date.desc(),
            )
            q = q.filter(
                or_(
                    Article.published_date >= cutoff,
                    Article.published_date.is_(None) & (Article.scraped_date >= cutoff),
                )
            )

            market_filter = self._build_market_filter(market)
            if market_filter is not None:
                q = q.filter(market_filter)

            topic_filter = self._build_topic_filter(topic)
            if topic_filter is not None:
                q = q.filter(topic_filter)

            articles = q.limit(limit).all()
            if not articles:
                return []

            ids = [a.id for a in articles if a.id]
            summaries = (
                db.query(StorySummary)
                .filter(StorySummary.article_id.in_(ids))
                .all()
            )
            summary_map = {s.article_id: s for s in summaries}

            out = []
            for a in articles:
                summary = summary_map.get(a.id)
                key_facts = self._parse_sources_json(summary.key_facts_json) if summary else None
                open_url = self._resolve_open_url(a.url, a.tags)
                out.append({
                    "id": a.id,
                    "title": a.title,
                    "source": a.source,
                    "published_date": a.published_date.isoformat() if a.published_date else None,
                    "url": a.url,
                    "open_url": open_url,
                    "summary_md": summary.summary_md if summary else None,
                    "key_facts": key_facts or None,
                })
            return out
        finally:
            db.close()

    def summarize_story(self, *, article_id: int, force: bool = False) -> Dict[str, Any]:
        db = SessionLocal()
        try:
            article = db.query(Article).filter(Article.id == int(article_id)).first()
            if not article:
                return {"error": "Article not found"}

            existing = db.query(StorySummary).filter(StorySummary.article_id == article.id).first()
            if existing and not force:
                return {
                    "article_id": article.id,
                    "summary_md": existing.summary_md,
                    "key_facts": self._parse_sources_json(existing.key_facts_json),
                    "cached": True,
                }
        finally:
            db.close()

        if not self.chat_service.enabled:
            return {"error": "AI service is not available."}

        content = (article.content or "")
        max_chars = 14000
        if len(content) > max_chars:
            content = content[:max_chars]

        system_prompt = """You are an expert data center real estate analyst.
Write concise, grounded summaries for DC real estate decision makers.

Rules:
- Use ONLY the provided article text.
- Do NOT add facts that aren't in the text.
- Output format exactly as specified."""

        user_prompt = f"""Summarize this article for data center real estate readers.

Title: {article.title}
Source: {article.source}
Published: {article.published_date.isoformat() if article.published_date else "unknown"}

Article text:
{content}

Output format exactly:
SUMMARY:
- bullet
- bullet

KEY_FACTS_JSON:
{{"market_metro":null,"address":null,"city":null,"state":null,"mw":null,"rack_kw":null,"capex":null,"sqft":null,"land_acres":null,"developer":null,"operator":null,"timeline":null,"permitting_status":null,"power_utility_iso":null,"stage":null}}

SO_WHAT:
- bullet"""

        summary_text = ""
        key_facts = {}
        try:
            raw = self.chat_service._llm(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=550,
                temperature=0.2,
            )
            summary_text, key_facts = self._parse_story_summary(raw)
        except Exception as e:
            logger.error(f"Story summary error: {e}")
            summary_text = ""
            key_facts = {}

        if not summary_text:
            return {"error": "Summary generation failed"}

        model_name = self.chat_service._select_chat_model()
        db = SessionLocal()
        try:
            row = db.query(StorySummary).filter(StorySummary.article_id == article.id).first()
            if row:
                row.summary_md = summary_text
                row.key_facts_json = json.dumps(key_facts or {})
                row.model = model_name
                row.created_at = datetime.utcnow()
            else:
                row = StorySummary(
                    article_id=article.id,
                    summary_md=summary_text,
                    key_facts_json=json.dumps(key_facts or {}),
                    model=model_name,
                )
                db.add(row)
            db.commit()
        finally:
            db.close()

        return {
            "article_id": article.id,
            "summary_md": summary_text,
            "key_facts": key_facts,
            "cached": False,
        }

    def generate_digest(
        self,
        *,
        date_obj: date,
        audience: str,
        window_days: int = 1,
    ) -> Dict[str, Any]:
        window_days = self._clamp_days(window_days)
        end_dt = datetime.combine(date_obj, datetime.min.time()) + timedelta(days=1)
        start_dt = end_dt - timedelta(days=window_days)

        candidates = self._load_articles(start_dt, end_dt)
        widened = False
        if len(candidates) < 4 and window_days < 7:
            window_days = 7
            start_dt = end_dt - timedelta(days=window_days)
            candidates = self._load_articles(start_dt, end_dt)
            widened = True

        if not candidates:
            return {
                "date": date_obj.isoformat(),
                "audience": audience,
                "title": f"Today’s Data Center Real Estate Digest ({date_obj.isoformat()})",
                "content_md": "No recent articles found for this window.",
                "sources": [],
                "meta": {"window_days": window_days, "coverage_thin": True, "sources": []},
            }

        query = "data center real estate development leasing land power permitting colocation hyperscale"
        retrieved = self.chat_service.retrieve_relevant_articles(query, n_results=60)
        candidate_urls = {c["url"] for c in candidates if c.get("url")}

        ranked = [r for r in retrieved if r.get("url") in candidate_urls]
        if len(ranked) < 30:
            ranked.extend([c for c in candidates if c.get("url") not in {r.get("url") for r in ranked}])

        deduped = self._dedupe_articles(ranked)[:50]

        theme_hints, clusters = self.chat_service._build_theme_hints(deduped, max_themes=5)
        selected = self._select_for_themes(deduped, clusters, max_sources=18)
        sources = [
            {"title": a.get("title") or "", "url": self._resolve_open_url(a.get("url"), a.get("tags")), "source": a.get("source") or ""}
            for a in selected
        ]

        system_prompt = """You are a data center real estate analyst. Be direct and specific.

Rules:
- Use ONLY the provided articles + context.
- Do NOT paste raw URLs in the body.
- Every factual claim tied to an article must carry an inline citation like [1].
- If coverage is thin and the window was widened, explicitly say so in "What changed".
- Use only dash bullets.
- Do NOT include a Sources section in the answer body.

Output format exactly:
## Today’s Data Center Real Estate Digest (YYYY-MM-DD)
### What changed
- bullet [n]

### Themes
### <Theme 1>
- bullet [n]

### Why it matters (for Data Center Real Estate)
- bullet [n]

### Deals and leasing signals (if present)
- bullet [n]

### Permitting and power constraints (if present)
- bullet [n]

### What to do next
- bullet [n]
"""

        context_text = self._build_context_text(selected)
        sources_block = "\n".join([f"{i}. {s['title']} — {s['source']}" for i, s in enumerate(sources, 1)])
        coverage_note = "Coverage thin; window widened to 7 days." if widened else "Coverage ok."

        user_prompt = f"""Date: {date_obj.isoformat()}
Audience: {audience}
Window days: {window_days}
Coverage note: {coverage_note}

Available Articles (numbered for citations):
{context_text}

Sources list to cite (exact; citations must refer to these numbers):
{sources_block}

{(theme_hints or "").strip()}
"""

        content_md = ""
        if self.chat_service.enabled:
            try:
                raw = self.chat_service._llm(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=900,
                    temperature=0.3,
                )
                content_md = self._clean_digest_output(raw, max_sources=len(sources))
            except Exception as e:
                logger.error(f"Digest generation error: {e}")
                content_md = ""

        if not content_md:
            content_md = "No digest generated."

        title = f"Today’s Data Center Real Estate Digest ({date_obj.isoformat()})"
        return {
            "date": date_obj.isoformat(),
            "audience": audience,
            "title": title,
            "content_md": content_md,
            "sources": sources,
            "meta": {
                "window_days": window_days,
                "coverage_thin": widened,
                "sources": sources,
            },
        }

    def _parse_date(self, date_str: Optional[str]) -> date:
        if date_str:
            try:
                return datetime.fromisoformat(date_str).date()
            except Exception:
                pass
        return datetime.utcnow().date()

    def _clamp_days(self, days: int) -> int:
        try:
            days = int(days)
        except Exception:
            days = 1
        return max(1, min(days, 30))

    def _load_articles(self, start_dt: datetime, end_dt: datetime) -> List[Dict[str, Any]]:
        db = SessionLocal()
        try:
            rows = (
                db.query(Article)
                .filter(
                    or_(
                        Article.published_date.between(start_dt, end_dt),
                        Article.published_date.is_(None) & Article.scraped_date.between(start_dt, end_dt),
                    )
                )
                .order_by(Article.published_date.desc().nullslast(), Article.scraped_date.desc())
                .limit(500)
                .all()
            )
            return [self._article_to_dict(a) for a in rows]
        finally:
            db.close()

    def _article_to_dict(self, a: Article) -> Dict[str, Any]:
        return {
            "title": a.title,
            "content": (a.content or "")[:2000],
            "url": a.url,
            "source": a.source,
            "source_type": a.source_type,
            "published_date": a.published_date.isoformat() if a.published_date else None,
            "tags": a.tags,
        }

    def _dedupe_articles(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        seen = set()
        for it in items:
            url = (it.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            out.append(it)
        return out

    def _select_for_themes(
        self,
        items: List[Dict[str, Any]],
        clusters: List[Dict[str, Any]],
        *,
        max_sources: int,
    ) -> List[Dict[str, Any]]:
        selected: List[Dict[str, Any]] = []
        if clusters:
            per_cluster = max(2, int(max_sources / max(1, len(clusters))))
            used = set()
            for c in clusters[:5]:
                count = 0
                for idx in c.get("indices", []):
                    if idx < 0 or idx >= len(items):
                        continue
                    url = (items[idx].get("url") or "").strip()
                    if not url or url in used:
                        continue
                    selected.append(items[idx])
                    used.add(url)
                    count += 1
                    if count >= per_cluster:
                        break
            for it in items:
                if len(selected) >= max_sources:
                    break
                url = (it.get("url") or "").strip()
                if not url or url in used:
                    continue
                selected.append(it)
                used.add(url)
        else:
            selected = items[:max_sources]
        return selected

    def _build_context_text(self, articles: List[Dict[str, Any]]) -> str:
        blocks = []
        for i, a in enumerate(articles, 1):
            content = (a.get("content") or "")
            content = re.sub(r"https?://\\S+", "[link]", content)
            blocks.append(
                f"[Source {i}]\nTitle: {a.get('title')}\nPublisher: {a.get('source')}\nPublished: {a.get('published_date')}\nContent: {content[:1200]}..."
            )
        return "\n\n".join(blocks)

    def _clean_digest_output(self, text: str, *, max_sources: int) -> str:
        raw = (text or "").strip()
        if not raw:
            return raw
        cleaned = re.sub(r"https?://\\S+", "", raw)
        cleaned = self.chat_service._strip_out_of_range_citations(cleaned, max_cite=max_sources)
        return cleaned.strip()

    def _parse_story_summary(self, raw: str) -> Tuple[str, Dict[str, Any]]:
        text = (raw or "").strip()
        if not text:
            return "", {}

        summary_lines = self._extract_section(text, "SUMMARY:", "KEY_FACTS_JSON:")
        so_what_lines = self._extract_section(text, "SO_WHAT:", None)
        summary_bullets = [ln for ln in summary_lines if ln.startswith("- ")]
        so_what_bullets = [ln for ln in so_what_lines if ln.startswith("- ")]
        if not so_what_bullets and so_what_lines:
            so_what_bullets = [f"- {so_what_lines[0].lstrip('- ').strip()}"]

        summary_md = "\n".join(summary_bullets + so_what_bullets).strip()
        key_facts = self._extract_json_block(text) or {}
        return summary_md, key_facts

    def _extract_section(self, text: str, start_label: str, end_label: Optional[str]) -> List[str]:
        start = text.find(start_label)
        if start < 0:
            return []
        section = text[start + len(start_label):]
        if end_label and end_label in section:
            section = section.split(end_label)[0]
        lines = [ln.strip() for ln in section.strip().splitlines() if ln.strip()]
        return lines

    def _extract_json_block(self, text: str) -> Dict[str, Any]:
        marker = "KEY_FACTS_JSON:"
        idx = text.find(marker)
        if idx < 0:
            return {}
        payload = text[idx + len(marker):]
        start = payload.find("{")
        if start < 0:
            return {}
        brace = 0
        end = None
        for i, ch in enumerate(payload[start:], start=start):
            if ch == "{":
                brace += 1
            elif ch == "}":
                brace -= 1
                if brace == 0:
                    end = i + 1
                    break
        if end is None:
            return {}
        block = payload[start:end]
        try:
            return json.loads(block)
        except Exception:
            return {}

    def _parse_sources_json(self, raw: Optional[str]) -> Dict[str, Any]:
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def _resolve_open_url(self, url: Optional[str], tags: Optional[str]) -> Optional[str]:
        if not url:
            return url
        if url.startswith("dcrundown://"):
            meta = self._parse_sources_json(tags or "")
            return meta.get("issue_url") or url
        return url

    def _build_market_filter(self, market: Optional[str]):
        if not market:
            return None
        key = market.strip().lower()
        mapping = {
            "dfw": ["dfw", "dallas", "fort worth", "dallas-fort worth", "north texas", "texas"],
            "nova": ["northern virginia", "n. virginia", "no. virginia", "loudoun", "ashburn", "sterling", "virginia"],
            "phoenix": ["phoenix", "mesa", "tempe", "arizona", "az"],
            "atlanta": ["atlanta", "georgia", "ga"],
            "chicago": ["chicago", "illinois", "il"],
            "ohio": ["ohio", "columbus", "new albany"],
            "ny": ["new york", "nj", "new jersey", "northern new jersey"],
        }
        terms = mapping.get(key, [market])
        return or_(*[Article.title.ilike(f"%{t}%") | Article.content.ilike(f"%{t}%") for t in terms])

    def _build_topic_filter(self, topic: Optional[str]):
        if not topic:
            return None
        key = topic.strip().lower()
        mapping = {
            "power": ["power", "grid", "substation", "interconnect", "utility"],
            "cooling": ["cooling", "liquid", "immersion", "direct-to-chip", "chiller"],
            "permitting": ["permit", "zoning", "entitlement", "moratorium"],
            "land": ["land", "acre", "site", "parcel"],
            "colocation": ["colocation", "colo", "multi-tenant"],
            "hyperscale": ["hyperscale", "hyperscaler", "campus"],
        }
        terms = mapping.get(key, [topic])
        return or_(*[Article.title.ilike(f"%{t}%") | Article.content.ilike(f"%{t}%") for t in terms])
