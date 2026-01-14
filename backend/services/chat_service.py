"""
RAG-based chat service for answering questions about data center news
"""
try:
    import openai
except ImportError:  # pragma: no cover
    openai = None
import os
from typing import List, Dict, Optional, Any, Tuple
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from uuid import uuid4
from .embedding_service import EmbeddingService
from .vector_store import VectorStore
from .cost_tracker import CostTracker
from ..database.models import Article, Conversation, Message
from ..database.db import SessionLocal
from ..scrapers.base_scraper import DC_RELEVANCE_KEYWORDS, EXCLUDE_KEYWORDS

# Load .env from multiple possible locations
env_paths = [
    Path(__file__).parent.parent / ".env",  # Backend folder (preferred)
    Path.cwd() / ".env",  # Current directory
    Path(__file__).parent.parent.parent / ".env",  # Project root
]

for env_path in env_paths:
    if env_path.exists():
        load_dotenv(env_path, override=True)
        break
else:
    load_dotenv()

logger = logging.getLogger(__name__)

class ChatService:
    """Service for handling chat queries using RAG"""
    
    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.vector_store = VectorStore()
        self.cost_tracker = CostTracker()
        
        # Try multiple providers in order: Groq (free), Together AI (free), OpenAI (paid)
        self.provider = os.getenv("AI_PROVIDER", "groq").lower()  # groq, together, openai
        self.enabled = False
        self.client = None
        
        if openai is None:
            logger.warning("openai SDK not installed. Chat providers (Groq/Together/OpenAI) will be disabled.")
            return
        
        if self.provider == "groq":
            groq_key = os.getenv("GROQ_API_KEY")
            if groq_key:
                try:
                    # Groq uses OpenAI-compatible API
                    self.client = openai.OpenAI(
                        api_key=groq_key,
                        base_url="https://api.groq.com/openai/v1"
                    )
                    self.enabled = True
                    logger.info("Using Groq API (free tier)")
                except Exception as e:
                    logger.error(f"Error initializing Groq: {e}")
        
        if not self.enabled and self.provider == "together":
            together_key = os.getenv("TOGETHER_API_KEY")
            if together_key:
                try:
                    self.client = openai.OpenAI(
                        api_key=together_key,
                        base_url="https://api.together.xyz/v1"
                    )
                    self.enabled = True
                    logger.info("Using Together AI (free tier)")
                except Exception as e:
                    logger.error(f"Error initializing Together AI: {e}")
        
        if not self.enabled:
            # Fallback to OpenAI
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                self.client = openai.OpenAI(api_key=api_key)
                self.enabled = True
                logger.info("Using OpenAI API (paid)")
            else:
                logger.warning("No AI provider configured. Chat will be disabled.")
    
    def retrieve_relevant_articles(self, query: str, n_results: int = 5) -> List[Dict]:
        """Retrieve relevant articles using semantic search or keyword fallback"""
        db = SessionLocal()
        articles = []
        
        try:
            # Try semantic search first only if the vector store has data
            vector_count = 0
            try:
                vector_count = self.vector_store.get_collection_size()
            except Exception:
                vector_count = 0
            
            if vector_count > 0:
                query_embedding = self.embedding_service.generate_embedding(query)
            else:
                query_embedding = None
            
            if query_embedding:
                similar_articles = self.vector_store.search_similar(query_embedding, n_results=max(n_results, 8))
                
                for article_data in similar_articles:
                    metadata = article_data.get('metadata', {})
                    doc = article_data.get("document") or ""

                    # Prefer metadata (chunked indexing stores full provenance); fall back to DB lookup if needed.
                    title = metadata.get("title") or ""
                    url = metadata.get("url") or ""
                    source = metadata.get("source") or ""
                    source_type = metadata.get("source_type") or ""
                    published_date = metadata.get("published_date")

                    if not title or not url:
                        article_id = metadata.get('article_id')
                        if article_id:
                            article = db.query(Article).filter(Article.id == article_id).first()
                            if article:
                                title = title or (article.title or "")
                                url = url or (article.url or "")
                                source = source or (article.source or "")
                                source_type = source_type or (article.source_type or "")
                                published_date = published_date or (article.published_date.isoformat() if article.published_date else None)
                                if not doc:
                                    doc = (article.content or "")[:2000]

                    if not title or not url:
                        continue

                    if not self._looks_like_datacenter_article(title, doc):
                        continue

                    articles.append({
                        'title': title,
                        'content': doc[:2000],
                        'url': url,
                        'source': source,
                        'source_type': source_type,
                        'published_date': published_date,
                    })
            
            # Fallback to keyword search if no semantic results
            if not articles:
                query_lower = query.lower()
                
                # Basic tokenization + stopword filtering
                tokens = re.findall(r"[a-z0-9]+", query_lower)
                stop = {
                    "the","a","an","and","or","to","of","in","on","for","with","about","latest",
                    "what","which","who","how","are","is","was","were","be","been","from",
                    "data","center","centers","datacenter","news",
                    # super-ambiguous terms that cause terrible matches
                    "site","sites","being"
                }
                query_words = [t for t in tokens if t not in stop and len(t) > 2]
                
                location_terms = self._location_terms(query_lower)
                if location_terms:
                    # add location hints as tokens (including common expansions)
                    for t in location_terms:
                        for part in re.findall(r"[a-z0-9]+", t.lower()):
                            if part and part not in stop:
                                query_words.append(part)
                
                # Intent expansion for common asks (construction/projects)
                construction_terms = {
                    "construction","build","building","built","project","projects","development",
                    "planned","planning","proposal","proposed","campus","facility","site",
                    "break","ground","megawatt","mw","expansion","expand"
                }
                if any(t in query_lower for t in ["construction", "projects", "build", "building", "break ground", "proposed", "planned"]):
                    query_words.extend(sorted(construction_terms))
                
                # Pull a larger, recent-ish candidate set
                candidates = db.query(Article).order_by(Article.published_date.desc()).limit(500).all()
                
                for article in candidates:
                    title_lower = (article.title or "").lower()
                    content_lower = (article.content or "").lower()

                    if not self._looks_like_datacenter_article(article.title or "", article.content or ""):
                        continue
                    
                    score = 0
                    for word in query_words:
                        if not word:
                            continue
                        if word in title_lower:
                            score += 5
                        if word in content_lower:
                            score += 1
                    
                    # Bonus for construction-like phrasing in title
                    if any(k in title_lower for k in ["mw", "megawatt", "data center", "datacenter", "campus", "build", "proposed", "planned", "break ground"]):
                        score += 2
                    
                    # If the query asks about a location, strongly prefer articles that mention it.
                    if location_terms:
                        if any(t in title_lower or t in content_lower for t in location_terms):
                            score += 15
                        else:
                            score -= 8
                    
                    if score > 0:
                        articles.append({
                            'title': article.title,
                            'content': (article.content or "")[:2000],
                            'url': article.url,
                            'source': article.source,
                            'source_type': article.source_type,
                            'published_date': article.published_date.isoformat() if article.published_date else None,
                            'score': score
                        })
                
                # Sort by score and take top results
                articles.sort(key=lambda x: (x.get('score', 0), x.get('published_date') or ""), reverse=True)
                articles = articles[:max(n_results, 10)]
                
                # Remove score before returning
                for article in articles:
                    article.pop('score', None)
        finally:
            db.close()
        
        return articles

    def _estimate_tokens(self, text: str) -> int:
        """
        Cheap token estimate (works without tokenizer deps).
        English-ish heuristic: ~4 chars/token with some slack for whitespace.
        """
        if not text:
            return 0
        return max(1, int(len(text) / 4))

    def _get_or_create_conversation(self, db, *, conversation_id: Optional[str], audience: Optional[str]) -> Conversation:
        cid = (conversation_id or "").strip() or str(uuid4())
        conv = db.query(Conversation).filter(Conversation.id == cid).first()
        if not conv:
            conv = Conversation(id=cid, audience=(audience or None), memory_summary=None)
            db.add(conv)
            db.commit()
            db.refresh(conv)
        else:
            # Best-effort audience persistence: keep first non-null, allow explicit override.
            if audience and audience.strip() and (conv.audience != audience.strip()):
                conv.audience = audience.strip()
                conv.updated_at = datetime.utcnow()
                db.commit()
        return conv

    def _load_recent_messages(self, db, *, conversation_id: str, limit: int = 12) -> List[Message]:
        limit = max(0, min(int(limit or 12), 50))
        if limit == 0:
            return []
        rows = (
            db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.id.desc())
            .limit(limit)
            .all()
        )
        return list(reversed(rows))

    def _count_conversation(self, db, *, conversation_id: str) -> Tuple[int, int]:
        """Return (message_count, token_est_total)."""
        rows = db.query(Message.tokens_est).filter(Message.conversation_id == conversation_id).all()
        msg_count = len(rows)
        tok_total = sum(int(r[0] or 0) for r in rows)
        return msg_count, tok_total

    def _maybe_summarize_and_prune(self, db, *, conv: Conversation) -> None:
        """
        If a conversation gets long, roll older turns into memory_summary and prune.
        Policy:
        - keep last KEEP_LAST messages
        - when message_count exceeds MAX_MESSAGES or token estimate exceeds MAX_TOKENS, summarize + delete older messages
        """
        max_messages = int(os.getenv("CONVERSATION_MAX_MESSAGES", "20") or "20")
        keep_last = int(os.getenv("CONVERSATION_KEEP_LAST", "12") or "12")
        max_tokens = int(os.getenv("CONVERSATION_MAX_TOKENS_EST", "8000") or "8000")

        keep_last = max(6, min(keep_last, 30))
        max_messages = max(keep_last + 2, min(max_messages, 200))
        max_tokens = max(2000, min(max_tokens, 50000))

        msg_count, tok_total = self._count_conversation(db, conversation_id=conv.id)
        if msg_count <= max_messages and tok_total <= max_tokens:
            return

        # Load older messages to summarize (everything except last keep_last)
        all_msgs = (
            db.query(Message)
            .filter(Message.conversation_id == conv.id)
            .order_by(Message.id.asc())
            .all()
        )
        if len(all_msgs) <= keep_last:
            return

        to_summarize = all_msgs[:-keep_last]
        to_keep = all_msgs[-keep_last:]

        # Build summarization prompt
        transcript = []
        for m in to_summarize:
            role = (m.role or "user").strip()
            content = (m.content or "").strip()
            if not content:
                continue
            transcript.append(f"{role.upper()}: {content}")

        transcript_text = "\n".join(transcript)
        if not transcript_text:
            return

        # If LLM is unavailable, do a crude truncation fallback.
        if not self.enabled or not self.client:
            existing = (conv.memory_summary or "").strip()
            combined = (existing + "\n" + transcript_text).strip()
            conv.memory_summary = combined[-6000:]
            conv.updated_at = datetime.utcnow()
            db.commit()
        else:
            system_prompt = """You are a conversation memory summarizer for a data center news assistant.
Your job is to compress older chat turns into a brief factual memory that helps future turns stay on-topic.

Rules:
- Be brief and factual.
- Use bullets only.
- Capture: user goals, preferences (audience/tone), key entities (companies/technologies/regions), and any constraints (time windows, rack density, MW, cooling type).
- Do NOT add new facts beyond the transcript.
- Do NOT include URLs.
"""
            existing = (conv.memory_summary or "").strip()
            user_prompt = f"""Existing memory (if any):
{existing if existing else "(none)"}

New transcript to fold into memory:
{transcript_text}

Write the updated memory summary as 6-14 bullet points."""
            try:
                summary = self._llm(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=350, temperature=0.2).strip()
            except Exception:
                summary = ""
            if summary:
                conv.memory_summary = summary
                conv.updated_at = datetime.utcnow()
                db.commit()

        # Prune older messages (delete everything except to_keep)
        keep_ids = {m.id for m in to_keep if m.id}
        if keep_ids:
            db.query(Message).filter(
                Message.conversation_id == conv.id,
                ~Message.id.in_(keep_ids),
            ).delete(synchronize_session=False)
            db.commit()

    def _router(self, query: str) -> Dict[str, Any]:
        """
        Lightweight intent + constraint router.
        This is intentionally heuristic-first to keep it cheap.
        """
        q = (query or "").strip()
        ql = q.lower()

        intent = "news_update"
        if any(k in ql for k in ["compare", "vs", "versus"]):
            intent = "compare"
        elif any(k in ql for k in ["recommend", "should we", "what should i", "what do you recommend"]):
            intent = "recommend"
        elif any(k in ql for k in ["explain", "what is", "how does", "definition"]):
            intent = "explain_concept"
        elif any(k in ql for k in ["forecast", "predict", "next 12 months", "outlook"]):
            intent = "forecast"
        elif any(k in ql for k in ["deal", "raise", "funding", "acquisition", "m&a"]):
            intent = "deal_monitor"
        elif any(k in ql for k in ["deep dive", "profile", "winners", "who are the winners", "who's winning", "leader"]):
            intent = "deep_dive_company"

        # Extract constraints
        constraints: Dict[str, Any] = {}

        mw = re.findall(r"(\d+(?:\.\d+)?)\s*mw\b", ql)
        if mw:
            constraints["power_mw"] = [float(x) for x in mw[:3]]

        kw = re.findall(r"(\d+(?:\.\d+)?)\s*kw\b", ql)
        if kw:
            constraints["rack_kw"] = [float(x) for x in kw[:3]]

        days = re.findall(r"last\s+(\d+)\s+days", ql)
        if days:
            constraints["time_window_days"] = int(days[0])

        cooling = []
        for k, label in [
            ("direct-to-chip", "direct_to_chip"),
            ("d2c", "direct_to_chip"),
            ("immersion", "immersion"),
            ("liquid cooling", "liquid_cooling"),
            ("rear door", "rear_door_hx"),
            ("crac", "facility_hvac"),
            ("crah", "facility_hvac"),
            ("chiller", "facility_hvac"),
        ]:
            if k in ql:
                cooling.append(label)
        if cooling:
            constraints["cooling_type"] = sorted(set(cooling))

        # Ambiguity detection: short, broad prompts without obvious anchors.
        ambiguous_topics = ["cooling innovations", "power constraints", "chip supply", "ai data centers", "site selection"]
        high_ambiguity = (len(ql.split()) <= 3) or any(t == ql for t in ambiguous_topics)

        clarifying_question = None
        if high_ambiguity and intent in {"news_update", "explain_concept"}:
            if "cooling" in ql:
                clarifying_question = "Quick clarifier: are you asking about facility cooling (chillers/CRAH/heat rejection) or chip-level cooling (direct-to-chip/immersion), and what rack density range (e.g., 20–40kW vs 60–100kW+)?"
            elif "power" in ql or "grid" in ql:
                clarifying_question = "Quick clarifier: which region/market (e.g., N. Virginia, DFW, Phoenix) and are you focused on near-term interconnect delays or longer-term capacity buildout?"
            else:
                clarifying_question = "Quick clarifier: what specific segment (hyperscalers vs colos vs enterprise) and what time window (last 7 days vs last 30 days) should I focus on?"

        return {
            "intent": intent,
            "constraints": constraints,
            "clarifying_question": clarifying_question,
        }

    def _select_chat_model(self) -> str:
        if self.provider == "groq":
            return os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        if self.provider == "together":
            return os.getenv("TOGETHER_MODEL", "meta-llama/Llama-3-8b-chat-hf")
        return os.getenv("OPENAI_CHAT_MODEL", "gpt-3.5-turbo")

    def _llm(self, *, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float) -> str:
        if not self.enabled or not self.client:
            raise RuntimeError("AI service is not available (missing API key or SDK).")

        # Cost pre-check (best-effort)
        if self.cost_tracker:
            self.cost_tracker.record_chat(user_prompt)

        resp = self.client.chat.completions.create(
            model=self._select_chat_model(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    def summarize_article(self, article_id: int, force: bool = False) -> Dict:
        """
        Generate (and cache) a high-signal summary for an article.
        Returns: {summary, article_id, title, url, source, published_date, cached}
        """
        db = SessionLocal()
        try:
            a = db.query(Article).filter(Article.id == int(article_id)).first()
            if not a:
                return {"error": "Article not found"}

            if a.summary and not force:
                return {
                    "article_id": a.id,
                    "title": a.title,
                    "url": a.url,
                    "source": a.source,
                    "published_date": a.published_date.isoformat() if a.published_date else None,
                    "summary": a.summary,
                    "cached": True,
                }

            if not self.enabled:
                return {"error": "AI service is not available. Configure GROQ_API_KEY / TOGETHER_API_KEY / OPENAI_API_KEY."}

            system_prompt = """You are an expert data center industry analyst.
Write a concise, high-signal article summary for an executive audience.

Rules:
- Use ONLY the provided article text.
- If details (MW, sqft, location, company, timeline, power/water constraints) are not present, say "not stated".
- Do not speculate. Do not add outside facts.

Format exactly:
## Executive summary
<2-4 sentences>

## Key facts
- Company/actor:
- Location/market:
- Project size/capacity (MW/sqft):
- Status (proposed/planned/under construction/operational):
- Timeline/date:
- Power/water/grid notes:

## Why it matters
<2-4 bullets>
"""

            content = (a.content or "")
            # Guardrail: don't send absurdly long content
            max_chars = int(os.getenv("SUMMARY_MAX_CHARS", "18000") or "18000")
            if max_chars > 0 and len(content) > max_chars:
                content = content[:max_chars]

            user_prompt = f"""Summarize this article.

Title: {a.title}
Source: {a.source}
Published: {a.published_date.isoformat() if a.published_date else "unknown"}
URL: {a.url}

Article text:
{content}
"""

            summary = self._llm(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=650, temperature=0.2).strip()

            a.summary = summary
            a.summary_model = self._select_chat_model()
            a.summary_created_at = datetime.utcnow()
            db.commit()

            return {
                "article_id": a.id,
                "title": a.title,
                "url": a.url,
                "source": a.source,
                "published_date": a.published_date.isoformat() if a.published_date else None,
                "summary": summary,
                "cached": False,
            }
        finally:
            db.close()

    def generate_digest(self, days: int = 7, limit: int = 12, topic: Optional[str] = None) -> Dict:
        """
        Generate an expert digest over recent articles using cached summaries when available.
        Returns: {answer, sources, meta}
        """
        if not self.enabled:
            return {"answer": "AI service is not available. Configure an API key to enable summaries/digests.", "sources": [], "meta": {}}

        days = max(1, min(int(days or 7), 30))
        limit = max(3, min(int(limit or 12), 30))

        db = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            q = db.query(Article).order_by(Article.published_date.desc().nullslast(), Article.scraped_date.desc())
            q = q.filter((Article.published_date == None) | (Article.published_date >= cutoff))  # noqa: E711
            if topic:
                term = f"%{topic}%"
                q = q.filter((Article.title.ilike(term)) | (Article.content.ilike(term)))
            items = q.limit(limit).all()
        finally:
            db.close()

        if not items:
            return {"answer": "No recent articles found for that window.", "sources": [], "meta": {"days": days, "limit": limit}}

        # Build digest context primarily from cached summaries (fallback to short content)
        blocks = []
        sources = []
        for i, a in enumerate(items, 1):
            published = a.published_date.isoformat() if a.published_date else None
            summary = a.summary or ""
            if not summary:
                # Avoid heavy per-article summarization in digest; fallback to snippet
                snippet = (a.content or "")[:800]
                summary = f"## Executive summary\n{snippet}\n"
            blocks.append(
                f"[Item {i}]\nTitle: {a.title}\nSource: {a.source}\nPublished: {published}\nURL: {a.url}\nSummary:\n{summary}\n"
            )
            sources.append({"title": a.title, "url": a.url, "source": a.source})

        system_prompt = """You are an expert data center industry analyst and operator-adjacent advisor.
Write a weekly-style digest that synthesizes themes and implications, not just a list.

Rules:
- Use ONLY the provided items.
- Cite by including (Source + URL) for each bullet or claim.
- If something is unclear, say so.

Output format exactly:
## Executive digest
<3-6 bullets>

## What’s changing (themes)
<3-6 bullets>

## Deals & capital
<bullets or 'None in provided items'>

## Construction & capacity
<bullets; include MW/sqft/location/status when present>

## Power, grid, and sustainability signals
<bullets>

## What to do next (actionable)
<5-8 bullets: questions to ask, risks to watch, follow-ups>
"""

        topic_line = f"Topic focus: {topic}" if topic else "Topic focus: general data center news"
        user_prompt = f"""Create a digest for the last {days} days. {topic_line}

Items:
{chr(10).join(blocks)}
"""

        answer = self._llm(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=900, temperature=0.3).strip()
        return {"answer": answer, "sources": sources, "meta": {"days": days, "limit": limit, "topic": topic}}

    def _location_terms(self, query_lower: str) -> List[str]:
        """
        Map common location shorthand to useful match terms.
        Keep this intentionally small and high-signal.
        """
        terms: List[str] = []
        if "dfw" in query_lower or "dallas" in query_lower or "fort worth" in query_lower:
            terms.extend([
                "dfw",
                "dallas",
                "fort worth",
                "dallas-fort worth",
                "dallas fort worth",
                "north texas",
                "texas",
                "tx",
                "irving",
                "plano",
                "allen",
                "frisco",
                "lancaster",
                "red oak",
                "mesquite",
                "garland",
                "arlington",
                "grand prairie",
            ])
        return terms

    def _looks_like_datacenter_article(self, title: str, content: str) -> bool:
        """
        Hard filter to prevent consumer-tech / parenting / gadget content from being used as context.
        Uses the same keyword sets as the scrapers, but as an allowlist-style guardrail.
        """
        t = f"{title} {content}".lower()
        if any(x in t for x in EXCLUDE_KEYWORDS):
            return False

        core = DC_RELEVANCE_KEYWORDS["high"]
        medium = DC_RELEVANCE_KEYWORDS["medium"]
        companies = DC_RELEVANCE_KEYWORDS["companies"]

        # Require at least one strong signal, or two medium signals
        if any(k in t for k in core):
            return True
        if any(k in t for k in companies):
            return True
        medium_hits = sum(1 for k in medium if k in t)
        if medium_hits >= 2:
            return True

        # Extra lightweight signals commonly present in construction/project coverage
        if any(k in t for k in ["mw", "megawatt", "substation", "power capacity", "data centre", "datacentre"]):
            return True

        return False

    def _store_articles(self, normalized_articles: List[Dict]) -> int:
        """Insert new articles into DB (best-effort, URL-unique). Returns count inserted."""
        if not normalized_articles:
            return 0
        db = SessionLocal()
        inserted = 0
        try:
            for a in normalized_articles:
                try:
                    exists = db.query(Article).filter(Article.url == a.get("url")).first()
                    if exists:
                        continue
                    db.add(Article(
                        title=a["title"],
                        content=a.get("content") or "",
                        url=a["url"],
                        source=a.get("source") or "",
                        source_type=a.get("source_type") or "unknown",
                        published_date=a.get("published_date"),
                        author=a.get("author"),
                        tags=a.get("tags"),
                        has_embedding=False,
                        embedding_id=None,
                    ))
                    inserted += 1
                except Exception:
                    continue
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
        return inserted

    def _proactive_fetch(self, query: str) -> int:
        """
        If we don't have good local matches, pull a small set of fresh, query-specific items
        (Baxtel RSS + Google News) and store them, so the next retrieval has something real.
        """
        query_lower = query.lower()
        location_terms = self._location_terms(query_lower)
        inserted_total = 0

        # 1) Baxtel RSS (very high-signal for projects)
        try:
            from ..scrapers.rss_scraper import RSSScraper
            rss = RSSScraper()
            raw = rss.parse_feed("https://baxtel.com/news.rss", "Baxtel News")
            normalized = []
            for a in raw:
                title = (a.get("title") or "").lower()
                content = (a.get("content") or "").lower()
                if location_terms and not any(t in title or t in content for t in location_terms):
                    continue
                n = rss.normalize_article(a)
                if n:
                    normalized.append(n)
            inserted_total += self._store_articles(normalized)
        except Exception as e:
            logger.debug(f"Proactive Baxtel fetch failed: {e}")

        # 2) Google News targeted queries (small + focused)
        try:
            from ..scrapers.google_news_scraper import GoogleNewsScraper
            g = GoogleNewsScraper()
            q_variants = []
            if location_terms:
                # Prefer explicit city strings over abbreviation
                q_variants.extend([
                    "Dallas Fort Worth data center construction",
                    "Dallas data center campus MW",
                    "Fort Worth data center proposed",
                    "Irving TX data center campus",
                    "Plano TX data center development",
                    "Lancaster TX data center",
                ])
            else:
                q_variants.append(query)

            normalized = []
            for q in q_variants[:3]:
                for a in g.search_google_news(q, limit=12):
                    n = g.normalize_article(a)
                    if n:
                        normalized.append(n)
            inserted_total += self._store_articles(normalized)
        except Exception as e:
            logger.debug(f"Proactive Google News fetch failed: {e}")

        return inserted_total
    
    def generate_response(
        self,
        query: str,
        context_articles: List[Dict],
        *,
        audience: Optional[str] = None,
        memory_summary: Optional[str] = None,
        recent_messages: Optional[List[Message]] = None,
    ) -> Dict:
        """Generate AI response using retrieved context"""
        if not self.enabled:
            return {
                'answer': "Sorry, the AI service is not available. Please configure your OpenAI API key.",
                'sources': []
            }
        
        # Build context from articles
        context_text = ""
        sources = []
        
        for i, article in enumerate(context_articles, 1):
            context_text += f"\n[Article {i}]\n"
            context_text += f"Title: {article['title']}\n"
            context_text += f"Source: {article['source']}\n"
            if article.get("published_date"):
                context_text += f"Published: {article['published_date']}\n"
            if article.get("source_type"):
                context_text += f"Source Type: {article['source_type']}\n"
            context_text += f"Content: {article['content'][:1200]}...\n"
            context_text += f"URL: {article['url']}\n"
            
            sources.append({
                'title': article['title'],
                'url': article['url'],
                'source': article['source'],
            })
        
        # Rundown-style by default. Force citations for any source-backed factual claim.
        system_prompt = """You are Data Center Rundown-style analyst: concise, high-signal, synthesis-first.

Hard rules:
- Use ONLY the provided articles + conversation context.
- Do NOT paste raw URLs in the body.
- Every factual claim tied to an article must carry at least one inline citation like [1].
- If retrieval is weak or stale, explicitly say so (e.g., "I’m not seeing strong coverage in the last X days") and suggest what to search.
- Adapt tone/depth to the requested audience: Exec, Investor, Operator, Engineer/Architect, Sustainability, Vendor.

Output format exactly:
## What changed recently
<3-6 bullets>

## Themes
### <Theme 1>
<2-4 bullets>
### <Theme 2>
<2-4 bullets>
### <Theme 3>
<2-4 bullets>
(3-5 themes total, only if supported by sources)

## Why it matters (for <audience>)
<3-6 bullets>

## If I were you
<3 actionable next steps>

## Sources
1. <Source title> — <Publisher>
2. ...
"""
        
        # Conversation context for continuity
        aud = (audience or "Exec").strip()
        mem = (memory_summary or "").strip()
        convo_lines = []
        for m in (recent_messages or []):
            role = (m.role or "").strip()
            if role not in {"user", "assistant"}:
                continue
            content = (m.content or "").strip()
            if not content:
                continue
            convo_lines.append(f"{role.upper()}: {content}")
        convo_context = "\n".join(convo_lines[-12:])

        user_prompt = f"""Audience: {aud}

Conversation memory (may be empty):
{mem if mem else "(none)"}

Recent conversation turns:
{convo_context if convo_context else "(none)"}

Question: {query}

Available Articles:
{context_text}

Write a Rundown-style synthesis. Use citations like [1] that map to the Sources list you produce at the end."""
        
        try:
            # Check cost limits before making API call
            if self.cost_tracker:
                try:
                    # Pre-check cost (estimate)
                    self.cost_tracker.record_chat(user_prompt)
                except Exception as e:
                    logger.error(f"Cost limit exceeded: {e}")
                    return {
                        'answer': "Sorry, I've reached the daily cost limit. Please try again tomorrow or adjust your cost limits in the .env file.",
                        'sources': []
                    }

            answer = self._llm(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=900, temperature=0.35)
            
            return {
                'answer': answer,
                'sources': sources
            }
        except Exception as e:
            logger.error(f"Error generating chat response: {e}")
            error_msg = str(e)
            if "cost limit" in error_msg.lower() or "limit exceeded" in error_msg.lower():
                return {
                    'answer': "I've reached the cost limit. Please check your usage or adjust limits in the .env file.",
                    'sources': []
                }
            return {
                'answer': f"Sorry, I encountered an error: {error_msg}",
                'sources': sources
            }
    
    def chat(
        self,
        query: str,
        history: Optional[List[Dict]] = None,
        audience: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> Dict:
        """Main chat method: server-side memory + retrieval + Rundown-style synthesis."""
        # If no articles in database, provide helpful message
        db = SessionLocal()
        try:
            conv = self._get_or_create_conversation(db, conversation_id=conversation_id, audience=audience)
            cid = conv.id

            # Persist the new user message
            db.add(Message(
                conversation_id=conv.id,
                role="user",
                content=query,
                tokens_est=self._estimate_tokens(query),
            ))
            conv.updated_at = datetime.utcnow()
            db.commit()

            # Summarize/prune if needed
            self._maybe_summarize_and_prune(db, conv=conv)

            total_articles = db.query(Article).count()
            if total_articles == 0:
                return {
                    'answer': "I don't have any articles in my database yet. The scraper runs every 30 minutes to collect news. Please wait a bit and try again, or ask me a general question about data centers and I'll do my best to help!",
                    'sources': [],
                    'conversation_id': conv.id,
                    'suggested_followups': ["Trigger a scrape", "Ask for a weekly digest", "Ask about a specific market (e.g., DFW, N. Virginia)"],
                }
        finally:
            db.close()
        
        # Router step (lightweight) to decide if we need a single clarifier.
        db = SessionLocal()
        try:
            conv = db.query(Conversation).filter(Conversation.id == cid).first()
            if not conv:
                conv = self._get_or_create_conversation(db, conversation_id=cid, audience=audience)
            route = self._router(query)
            if route.get("clarifying_question"):
                clarifier = str(route["clarifying_question"]).strip()
                db.add(Message(
                    conversation_id=conv.id,
                    role="assistant",
                    content=clarifier,
                    tokens_est=self._estimate_tokens(clarifier),
                ))
                conv.updated_at = datetime.utcnow()
                db.commit()
                return {
                    "answer": clarifier,
                    "sources": [],
                    "conversation_id": conv.id,
                    "suggested_followups": [],
                }

            # Load memory + last N turns for continuity
            recent_messages = self._load_recent_messages(db, conversation_id=conv.id, limit=12)
            memory_summary = (conv.memory_summary or "").strip() or None
            aud = (audience or conv.audience or "Exec").strip()
        finally:
            db.close()

        # Retrieve more candidates to support themes, then let the LLM cluster/synthesize.
        articles = self.retrieve_relevant_articles(query, n_results=40)
        
        # Proactive fallback: if it's a location question and we didn't retrieve any location hits,
        # try to fetch a few fresh, location-specific items and re-run retrieval once.
        query_lower = query.lower()
        loc_terms = self._location_terms(query_lower)
        if loc_terms:
            have_loc = any(
                any(t in (a.get("title","").lower() + " " + a.get("content","").lower()) for t in loc_terms)
                for a in articles
            )
            if not have_loc:
                inserted = self._proactive_fetch(query)
                if inserted > 0:
                    articles = self.retrieve_relevant_articles(query, n_results=40)
        
        if not articles:
            # Persist assistant reply
            db = SessionLocal()
            try:
                conv = self._get_or_create_conversation(db, conversation_id=cid, audience=audience)
                msg = "I couldn't find any strong coverage for that query. Try specifying a time window (last 7–30 days), region/market, and any constraints (MW, rack kW, cooling type)."
                db.add(Message(conversation_id=conv.id, role="assistant", content=msg, tokens_est=self._estimate_tokens(msg)))
                conv.updated_at = datetime.utcnow()
                db.commit()
            finally:
                db.close()
            return {
                'answer': "I couldn't find any strong coverage for that query. Try specifying a time window (last 7–30 days), region/market, and any constraints (MW, rack kW, cooling type).",
                'sources': [],
                'conversation_id': cid,
                'suggested_followups': ["Last 7 days", "Focus on a specific market", "Compare two cooling options for a rack density"],
            }
        
        # Generate response
        result = self.generate_response(
            query,
            articles[:25],  # cap context size
            audience=aud,
            memory_summary=memory_summary,
            recent_messages=recent_messages,
        )

        # Persist assistant reply
        db = SessionLocal()
        try:
            conv = self._get_or_create_conversation(db, conversation_id=cid, audience=aud)
            ans = (result.get("answer") or "").strip()
            if ans:
                db.add(Message(
                    conversation_id=conv.id,
                    role="assistant",
                    content=ans,
                    tokens_est=self._estimate_tokens(ans),
                ))
                conv.updated_at = datetime.utcnow()
                db.commit()
            result["conversation_id"] = conv.id
            # Basic follow-up suggestions (cheap heuristic)
            result["suggested_followups"] = [
                "Compare two approaches in more detail",
                "Who are the winners / leading vendors?",
                "What should I watch over the next 30–90 days?",
            ]
        finally:
            db.close()

        return result
