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
        articles: List[Dict[str, Any]] = []
        
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

                # Deduplicate by article_id/url, keeping the best (lowest distance) chunk per article.
                best: Dict[str, Dict[str, Any]] = {}
                for article_data in similar_articles:
                    metadata = article_data.get('metadata', {})
                    doc = article_data.get("document") or ""
                    distance = article_data.get("distance")

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

                    key = str(metadata.get("article_id") or url)
                    candidate = {
                        'title': title,
                        'content': doc[:2000],
                        'url': url,
                        'source': source,
                        'source_type': source_type,
                        'published_date': published_date,
                        'distance': distance,
                    }
                    prev = best.get(key)
                    if prev is None:
                        best[key] = candidate
                    else:
                        # Prefer smaller distance; if missing, keep the first.
                        try:
                            if distance is not None and (prev.get("distance") is None or float(distance) < float(prev.get("distance"))):
                                best[key] = candidate
                        except Exception:
                            pass

                articles = list(best.values())
                articles.sort(key=lambda x: (x.get("distance") is None, x.get("distance") or 0.0))
                # Drop internal scoring keys
                for a in articles:
                    a.pop("distance", None)
                articles = articles[:max(n_results, 10)]
            
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
                # Deduplicate by URL in keyword mode
                seen_urls = set()
                deduped = []
                for a in articles:
                    u = a.get("url")
                    if not u or u in seen_urls:
                        continue
                    seen_urls.add(u)
                    deduped.append(a)
                articles = deduped[:max(n_results, 10)]
                
                # Remove score before returning
                for article in articles:
                    article.pop('score', None)
        finally:
            db.close()
        
        return articles

    def _parse_time_window_days(self, query: str) -> Optional[int]:
        ql = (query or "").lower()
        # last N days
        m = re.search(r"last\\s+(\\d{1,3})\\s+days", ql)
        if m:
            try:
                return max(1, min(365, int(m.group(1))))
            except Exception:
                return None
        # this week / past week
        if any(k in ql for k in ["this week", "past week", "last week"]):
            return 7
        # this month / past month
        if any(k in ql for k in ["this month", "past month", "last month"]):
            return 30
        # recent/latest default handled elsewhere
        return None

    def _dedupe_and_cap_sources(self, items: List[Dict[str, Any]], *, max_sources: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Return (selected_items, sources[]) where:
        - sources are deduped by URL and capped
        - selected_items are aligned to sources order (same URL ordering)
        """
        max_sources = max(1, min(int(max_sources or 10), 25))
        seen = set()
        selected = []
        sources = []
        for it in items:
            url = (it.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            selected.append(it)
            sources.append({"title": it.get("title") or "", "url": url, "source": it.get("source") or ""})
            if len(sources) >= max_sources:
                break
        return selected, sources

    def _strip_out_of_range_citations(self, text: str, *, max_cite: int) -> str:
        if not text:
            return text
        max_cite = int(max_cite or 0)
        if max_cite <= 0:
            # remove all citations if no sources
            return re.sub(r"\[(\d+)\]", "", text)

        def _repl(m):
            try:
                n = int(m.group(1))
            except Exception:
                return ""
            return m.group(0) if 1 <= n <= max_cite else ""

        return re.sub(r"\[(\d+)\]", _repl, text)

    def _filter_by_recency_days(self, articles: List[Dict[str, Any]], *, days: int) -> List[Dict[str, Any]]:
        """
        Keep only articles with published_date within the last N days.
        If published_date is missing/unparseable, drop it for recency-filtered intents.
        """
        try:
            days = int(days)
        except Exception:
            return articles
        if days <= 0:
            return articles
        cutoff = datetime.utcnow() - timedelta(days=days)

        out: List[Dict[str, Any]] = []
        for a in articles or []:
            pd = a.get("published_date")
            if not pd:
                continue
            try:
                if isinstance(pd, datetime):
                    dt = pd
                else:
                    dt = datetime.fromisoformat(str(pd).replace("Z", "+00:00"))
                if dt.tzinfo is not None:
                    dt = dt.astimezone(tz=None).replace(tzinfo=None)
                if dt >= cutoff:
                    out.append(a)
            except Exception:
                continue
        return out

    def _normalize_vec(self, v: List[float]) -> List[float]:
        s = 0.0
        for x in v:
            s += float(x) * float(x)
        if s <= 0.0:
            return v
        inv = (s ** 0.5)
        return [float(x) / inv for x in v]

    def _cos_sim(self, a: List[float], b: List[float]) -> float:
        s = 0.0
        for x, y in zip(a, b):
            s += float(x) * float(y)
        return float(s)

    def _kmeans_cosine(self, vectors: List[List[float]], k: int, iters: int = 7) -> List[int]:
        """
        Very small, dependency-free k-means using cosine similarity.
        Returns cluster assignment per vector.
        """
        n = len(vectors)
        if n == 0:
            return []
        k = max(1, min(int(k), n))
        vs = [self._normalize_vec(v) for v in vectors]

        # Deterministic "farthest-first" init
        centroids = [vs[0]]
        while len(centroids) < k:
            best_i = 0
            best_d = None
            for i in range(n):
                sims = [self._cos_sim(vs[i], c) for c in centroids]
                d = 1.0 - max(sims)
                if best_d is None or d > best_d:
                    best_d = d
                    best_i = i
            centroids.append(vs[best_i])

        assign = [0] * n
        for _ in range(iters):
            # assign
            for i in range(n):
                best_j = 0
                best_s = None
                for j in range(k):
                    s = self._cos_sim(vs[i], centroids[j])
                    if best_s is None or s > best_s:
                        best_s = s
                        best_j = j
                assign[i] = best_j
            # recompute
            sums = [[0.0] * len(vs[0]) for _ in range(k)]
            counts = [0] * k
            for i in range(n):
                j = assign[i]
                counts[j] += 1
                vi = vs[i]
                for d in range(len(vi)):
                    sums[j][d] += vi[d]
            for j in range(k):
                if counts[j] == 0:
                    continue
                centroids[j] = self._normalize_vec([x / counts[j] for x in sums[j]])
        return assign

    def _cluster_label(self, titles: List[str]) -> str:
        """Cheap labeler grounded in titles."""
        t = " ".join(titles).lower()
        buckets = [
            ("Cooling & thermal", ["cool", "immersion", "direct-to-chip", "d2c", "liquid", "rear-door", "cdu"]),
            ("Power & grid", ["power", "grid", "interconnect", "substation", "utility", "transformer"]),
            ("Deals & capital", ["fund", "raise", "investment", "acquir", "m&a", "deal"]),
            ("Permitting & policy", ["permit", "zoning", "regulat", "moratorium", "policy"]),
            ("Markets & site selection", ["site", "campus", "build", "construction", "lease", "virginia", "dfw", "phoenix", "ohio", "ireland", "singapore"]),
            ("AI & compute demand", ["ai", "gpu", "nvidia", "training", "inference"]),
        ]
        best = ("Themes", 0)
        for name, keys in buckets:
            score = sum(1 for k in keys if k in t)
            if score > best[1]:
                best = (name, score)
        return best[0]

    def _build_theme_hints(
        self,
        items: List[Dict[str, Any]],
        *,
        max_themes: int = 3,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Cluster candidates and return (theme_hints_text, clusters) where clusters contain:
        {label, indices}
        """
        # Dedupe by URL while preserving order
        deduped = []
        seen = set()
        for a in items:
            u = (a.get("url") or "").strip()
            if not u or u in seen:
                continue
            seen.add(u)
            deduped.append(a)
            if len(deduped) >= 50:
                break

        if len(deduped) < 4:
            return "", []

        reps = []
        for a in deduped:
            title = (a.get("title") or "").strip()
            snippet = (a.get("content") or "").strip().replace("\n", " ")
            reps.append((title + "\n" + snippet[:280]).strip())

        clusters: List[Dict[str, Any]] = []

        if getattr(self.embedding_service, "enabled", False):
            embs = self.embedding_service.generate_embeddings_batch(reps)
            ok = [(i, e) for i, e in enumerate(embs) if e]
            if len(ok) >= 6:
                vecs = [e for _, e in ok]
                n = len(vecs)
                k = 3 if n < 14 else (4 if n < 28 else 5)
                assign = self._kmeans_cosine(vecs, k=k, iters=7)
                by = {}
                for (orig_i, _), c in zip(ok, assign):
                    by.setdefault(int(c), []).append(orig_i)
                for _, idxs in sorted(by.items(), key=lambda kv: len(kv[1]), reverse=True):
                    titles = [(deduped[i].get("title") or "") for i in idxs[:8]]
                    clusters.append({"label": self._cluster_label(titles), "indices": idxs})
            else:
                # fall back to keyword grouping
                clusters = []

        if not clusters:
            # Keyword-based grouping fallback (cheap, no LLM required)
            by_label: Dict[str, List[int]] = {}
            for i, a in enumerate(deduped):
                label = self._cluster_label([(a.get("title") or "")])
                by_label.setdefault(label, []).append(i)
            for label, idxs in sorted(by_label.items(), key=lambda kv: len(kv[1]), reverse=True):
                clusters.append({"label": label, "indices": idxs})

        clusters = clusters[:max(1, min(max_themes, 5))]
        hint_lines = []
        for c in clusters[:max_themes]:
            idxs = c["indices"][:6]
            titles = [deduped[i].get("title") or "" for i in idxs]
            hint_lines.append(f"- {c['label']}: " + "; ".join(titles[:4]))
        theme_hints = "Theme candidates (clustered from retrieved items):\n" + "\n".join(hint_lines)
        return theme_hints, clusters

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
        mode: Optional[str] = None
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

        # Special mode: construction projects roundup
        if any(k in ql for k in ["construction projects", "latest construction projects", "data center construction", "new builds", "breaking ground"]):
            mode = "construction_projects"

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
            "mode": mode,
        }

    def _clean_rundown_answer(self, answer: str, *, audience: str, max_sources: int) -> str:
        """
        Enforce clean, scannable Rundown layout:
        - Remove any Sources section (API returns sources separately)
        - Normalize bullets to "- "
        - Keep only allowed headers and bounded bullets/themes
        """
        raw = (answer or "").strip()
        if not raw:
            return raw

        # Hard remove any trailing sources section (several variants)
        lines = raw.splitlines()
        cut_idx = None
        for i, ln in enumerate(lines):
            low = ln.strip().lower()
            if low.startswith("## sources") or low == "sources" or low.startswith("sources:"):
                cut_idx = i
                break
        if cut_idx is not None:
            lines = lines[:cut_idx]

        # Normalize bullet markers ("* ", "• ", numbered) -> "- "
        norm = []
        for ln in lines:
            s = ln.rstrip()
            ls = s.lstrip()
            if ls.startswith("* ") or ls.startswith("• "):
                indent = s[: len(s) - len(s.lstrip())]
                s = indent + "- " + ls[2:]
            else:
                m = re.match(r"^(\\s*)\\d+\\.\\s+(.*)$", s)
                if m:
                    s = f"{m.group(1)}- {m.group(2)}"
            norm.append(s)
        lines = norm

        # Remove out-of-range citations early (then bullets may be dropped for having no citations)
        lines = self._strip_out_of_range_citations("\n".join(lines), max_cite=max_sources).splitlines()

        aud = (audience or "Exec").strip()
        allowed_headers = {
            "## what changed recently": "## What changed recently",
            "## themes": "## Themes",
            "## why it matters": f"## Why it matters (for {aud})",
            "## why it matters (for": f"## Why it matters (for {aud})",
            "## if i were you": "## If I were you",
        }

        out: List[str] = []
        section = None  # what/themes/why/if
        what_bullets = 0
        why_bullets = 0
        if_bullets = 0
        theme_count = 0
        theme_bullets = 0
        in_themes = False

        def push_blank():
            if out and out[-1].strip() != "":
                out.append("")

        for ln in lines:
            t = (ln or "").strip()
            if not t:
                continue

            tl = t.lower()
            if tl.startswith("## "):
                # Normalize known headers; drop unknown ones to reduce spam
                key = None
                for k in allowed_headers.keys():
                    if tl.startswith(k):
                        key = k
                        break
                if not key:
                    continue

                hdr = allowed_headers[key]
                # Ensure stable order by just writing as we encounter; model is usually ordered already.
                push_blank()
                out.append(hdr if hdr != "## Why it matters" else hdr)
                section = "themes" if hdr.lower() == "## themes" else (
                    "what" if hdr.lower() == "## what changed recently" else (
                        "why" if hdr.lower().startswith("## why it matters") else "if"
                    )
                )
                in_themes = (section == "themes")
                if section == "themes":
                    theme_count = 0
                    theme_bullets = 0
                continue

            # Theme subheaders only within Themes
            if t.startswith("###"):
                if not in_themes:
                    continue
                if theme_count >= 3:
                    continue
                push_blank()
                out.append(t)
                theme_count += 1
                theme_bullets = 0
                continue

            # Keep only dash bullets
            if t.startswith("- "):
                has_cite = bool(re.search(r"\[\d+\]", t))
                if section == "what":
                    if what_bullets >= 5:
                        continue
                    if not has_cite:
                        continue
                    out.append(t)
                    what_bullets += 1
                    continue
                if section == "why":
                    if why_bullets >= 3:
                        continue
                    if not has_cite:
                        continue
                    out.append(t)
                    why_bullets += 1
                    continue
                if section == "if":
                    if if_bullets >= 3:
                        continue
                    out.append(t)
                    if_bullets += 1
                    continue
                if section == "themes":
                    # Only include bullets if we have at least one theme header already
                    if theme_count <= 0:
                        continue
                    if theme_bullets >= 3:
                        continue
                    if not has_cite:
                        continue
                    out.append(t)
                    theme_bullets += 1
                    continue
                continue

            # Drop other prose lines to keep it scannable
            continue

        cleaned = "\n".join(out).strip()
        cleaned = self._strip_out_of_range_citations(cleaned, max_cite=max_sources)
        return cleaned

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
        response_meta: Optional[Dict[str, Any]] = None,
        theme_hints: Optional[str] = None,
    ) -> Dict:
        """Generate AI response using retrieved context"""
        if not self.enabled:
            return {
                'answer': "Sorry, the AI service is not available. Please configure your OpenAI API key.",
                'sources': []
            }
        
        # Build context from articles (sources are backend-controlled/capped upstream)
        context_text = ""
        sources = []

        # Simple recency signal to help the model call out weak/stale retrieval.
        published_dates = []
        
        for i, article in enumerate(context_articles, 1):
            context_text += f"\n[Source {i}]\n"
            context_text += f"Title: {article['title']}\n"
            context_text += f"Publisher: {article['source']}\n"
            if article.get("published_date"):
                context_text += f"Published: {article['published_date']}\n"
                published_dates.append(article.get("published_date"))
            if article.get("source_type"):
                context_text += f"Source Type: {article['source_type']}\n"
            # Prevent raw URLs from showing up in the model prompt body.
            content = (article.get("content") or "")
            content = re.sub(r"https?://\\S+", "[link]", content)
            context_text += f"Content: {content[:1200]}...\n"
            
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
- Every factual claim tied to an article must carry at least one inline citation like [1] that refers to the provided Sources list.
- If retrieval is weak or stale, explicitly say so (e.g., "I’m not seeing strong coverage in the last X days") and suggest what to search.
- Adapt tone/depth to the requested audience: Exec, Investor, Operator, Engineer/Architect, Sustainability, Vendor.
- Use ONLY dash bullets: every bullet line MUST start with "- " (dash + space). Do not use "*" bullets.
- Do NOT include a "Sources" section in the answer (sources are shown separately in the UI). Only cite inline like [1].
- No filler: any bullet in "What changed recently", "Themes", or "Why it matters" MUST include at least one citation like [1].
- Themes must be grounded: use the provided "Theme candidates" (clustered from retrieved items) to name themes and avoid repetition.
- When possible, each theme should cite 2+ different sources across its bullets (not the same [1] repeatedly).
- "Why it matters" bullets must explicitly connect a cited item to an implication (e.g., "Because [3] indicates X, expect Y…").

Length limits (strict):
- "What changed recently": max 5 bullets.
- "Themes": max 3 themes, max 3 bullets per theme.
- "Why it matters": max 3 bullets.
- "If I were you": max 3 bullets.

Output format exactly:
## What changed recently
<bullets only>

## Themes
### <Theme 1>
<bullets only>
### <Theme 2>
<bullets only>
### <Theme 3>
<bullets only>

## Why it matters (for <audience>)
<bullets only>

## If I were you
<bullets only>
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

        # Best-effort: compute "days since newest item" (ISO parsing may fail; ok).
        newest_days = None
        try:
            newest_iso = None
            for p in published_dates:
                if p and (newest_iso is None or str(p) > str(newest_iso)):
                    newest_iso = p
            if newest_iso:
                newest_dt = datetime.fromisoformat(str(newest_iso).replace("Z", "+00:00"))
                newest_days = max(0, (datetime.utcnow().replace(tzinfo=newest_dt.tzinfo) - newest_dt).days)
        except Exception:
            newest_days = None

        sources_block = "\n".join([f"{i}. {s['title']} — {s['source']}" for i, s in enumerate(sources, 1)])

        # Lightweight mode hinting (construction projects)
        query_lower = (query or "").lower()
        construction_mode = any(k in query_lower for k in ["construction projects", "latest construction projects", "data center construction", "breaking ground", "new builds"])

        user_prompt = f"""Audience: {aud}
Mode: {"construction_projects" if construction_mode else "default"}

Recency note: newest provided item is {newest_days if newest_days is not None else "unknown"} days old.
Time window: last {((response_meta or {}).get("time_window_days")) if response_meta else "unknown"} days.

Conversation memory (may be empty):
{mem if mem else "(none)"}

Recent conversation turns:
{convo_context if convo_context else "(none)"}

Question: {query}

Available Articles (numbered for citations):
{context_text}

Sources list to cite (exact; citations must refer to these numbers):
{sources_block}

{(theme_hints or "").strip()}

Task:
- Write the Rundown-style sections exactly as specified.
- Use inline citations like [1] that refer to the sources list above.
- Do NOT include a Sources section in the answer body.

Construction projects mode instructions (only if Mode=construction_projects):
- In "What changed recently", every bullet should be a concrete project item (company/project name — location — size/capex/MW if stated) with a citation.
- If size/capex/MW isn't in sources, omit it (do not invent).
"""
        
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

            answer = self._llm(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=850, temperature=0.25)
            answer = self._clean_rundown_answer(answer, audience=aud, max_sources=len(sources))
            
            return {
                'answer': answer,
                'sources': sources,
                'meta': response_meta or {},
            }
        except Exception as e:
            logger.error(f"Error generating chat response: {e}")
            error_msg = str(e)
            if "cost limit" in error_msg.lower() or "limit exceeded" in error_msg.lower():
                return {
                    'answer': "I've reached the cost limit. Please check your usage or adjust limits in the .env file.",
                    'sources': [],
                    'meta': response_meta or {},
                }
            return {
                'answer': f"Sorry, I encountered an error: {error_msg}",
                'sources': sources,
                'meta': response_meta or {},
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
                    'meta': {"time_window_days": None, "sources_used": 0, "coverage_thin": False, "widened_to_days": None, "semantic_enabled": False},
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
                    "meta": {"time_window_days": None, "sources_used": 0, "coverage_thin": False, "widened_to_days": None, "semantic_enabled": bool(getattr(self.embedding_service, "enabled", False) and self.vector_store.get_collection_size() > 0)},
                }

            # Load memory + last N turns for continuity
            recent_messages = self._load_recent_messages(db, conversation_id=conv.id, limit=12)
            memory_summary = (conv.memory_summary or "").strip() or None
            aud = (audience or conv.audience or "Exec").strip()
            constraints = route.get("constraints") or {}
            intent = route.get("intent") or "news_update"
            mode = route.get("mode")
        finally:
            db.close()

        # Recency window (default last 14 days for "latest/news/deals/construction" intents; overridable).
        requested_days = self._parse_time_window_days(query)
        default_days = 14 if (intent in {"news_update", "deal_monitor"} or mode == "construction_projects") else None
        time_window_days = requested_days or default_days
        widened = False
        coverage_thin = False

        # Retrieve more candidates to support themes, then cluster/synthesize.
        search_query = query
        try:
            extras = []
            cooling = constraints.get("cooling_type") or []
            for c in cooling:
                if c == "direct_to_chip":
                    extras.extend(["direct-to-chip", "d2c"])
                elif c == "immersion":
                    extras.append("immersion")
                elif c == "rear_door_hx":
                    extras.extend(["rear-door", "heat exchanger"])
                elif c == "facility_hvac":
                    extras.extend(["chiller", "CRAH", "CRAC"])
            rack_kw = constraints.get("rack_kw") or []
            for k in rack_kw:
                try:
                    extras.append(f"{int(k)}kW")
                except Exception:
                    pass
            power_mw = constraints.get("power_mw") or []
            for m in power_mw:
                try:
                    extras.append(f"{int(m)}MW")
                except Exception:
                    pass
            if extras:
                search_query = f"{query} {' '.join(sorted(set(extras)))}"
        except Exception:
            search_query = query

        # Pull a larger candidate set so recency filtering can still find enough.
        candidate_pool = self.retrieve_relevant_articles(search_query, n_results=80)
        articles = candidate_pool

        if time_window_days:
            articles = self._filter_by_recency_days(candidate_pool, days=int(time_window_days))
            if len(articles) < 4 and (requested_days is None) and int(time_window_days) < 30:
                # Auto-widen to 30 days, but surface this via meta/UI (not via uncited bullets).
                coverage_thin = True
                widened = True
                time_window_days = 30
                articles = self._filter_by_recency_days(candidate_pool, days=30)
        
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
                    candidate_pool = self.retrieve_relevant_articles(search_query, n_results=80)
                    articles = candidate_pool
                    if time_window_days:
                        articles = self._filter_by_recency_days(candidate_pool, days=int(time_window_days))
        
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
                'meta': {
                    "time_window_days": time_window_days or None,
                    "sources_used": 0,
                    "coverage_thin": coverage_thin,
                    "widened_to_days": 30 if widened else None,
                    "semantic_enabled": bool(getattr(self.embedding_service, "enabled", False) and self.vector_store.get_collection_size() > 0),
                },
            }
        
        # Cluster candidates (real clustering when embeddings are enabled) to build grounded theme hints.
        theme_hints, clusters = self._build_theme_hints(articles, max_themes=3)

        # Backend-controlled sources list (dedupe + cap) to keep citations stable in the UI.
        # Prefer selecting from top clusters to make Themes distinct and grounded.
        # Hard cap at 10 so citations always map to UI sources.
        max_sources = 10
        # Deduped list for selection
        deduped = []
        seen = set()
        for a in articles:
            u = (a.get("url") or "").strip()
            if not u or u in seen:
                continue
            seen.add(u)
            deduped.append(a)
            if len(deduped) >= 50:
                break

        selected: List[Dict[str, Any]] = []
        if clusters:
            # Map cluster indices over deduped list (as built in _build_theme_hints)
            # Select up to ~even spread across top clusters
            per_cluster = max(2, int((max_sources + 2) / 3))
            selected_urls = set()
            for c in clusters[:3]:
                count = 0
                for idx in c.get("indices", []):
                    if idx < 0 or idx >= len(deduped):
                        continue
                    u = (deduped[idx].get("url") or "").strip()
                    if not u or u in selected_urls:
                        continue
                    selected.append(deduped[idx])
                    selected_urls.add(u)
                    count += 1
                    if count >= per_cluster:
                        break
            # Fill remainder
            for a in deduped:
                if len(selected) >= max_sources:
                    break
                u = (a.get("url") or "").strip()
                if not u or u in selected_urls:
                    continue
                selected.append(a)
                selected_urls.add(u)
        else:
            selected = deduped

        selected_articles, sources = self._dedupe_and_cap_sources(selected, max_sources=max_sources)

        response_meta = {
            "time_window_days": time_window_days or None,
            "sources_used": len(sources),
            "coverage_thin": coverage_thin,
            "widened_to_days": 30 if widened else None,
            "semantic_enabled": bool(getattr(self.embedding_service, "enabled", False) and self.vector_store.get_collection_size() > 0),
        }

        # Generate response (only from selected sources)
        result = self.generate_response(
            query,
            selected_articles,
            audience=aud,
            memory_summary=memory_summary,
            recent_messages=recent_messages,
            response_meta=response_meta,
            theme_hints=theme_hints,
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
