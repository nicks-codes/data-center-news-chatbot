"""
RAG-based chat service for answering questions about data center news
"""
try:
    import openai
except ImportError:  # pragma: no cover
    openai = None
import os
from typing import List, Dict, Optional
import logging
import re
from pathlib import Path
from dotenv import load_dotenv
from .embedding_service import EmbeddingService
from .vector_store import VectorStore
from .cost_tracker import CostTracker
from ..database.models import Article
from ..database.db import SessionLocal

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
                    article_id = metadata.get('article_id')
                    vector_id = article_data.get('id')
                    
                    article = None
                    if article_id:
                        article = db.query(Article).filter(Article.id == article_id).first()
                    
                    if not article and vector_id:
                        article = db.query(Article).filter(Article.embedding_id == vector_id).first()
                    
                    if article:
                        articles.append({
                            'title': article.title,
                            'content': article.content,
                            'url': article.url,
                            'source': article.source,
                            'source_type': article.source_type,
                            'published_date': article.published_date.isoformat() if article.published_date else None,
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
            ])
        return terms

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
    
    def generate_response(self, query: str, context_articles: List[Dict]) -> Dict:
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
        
        # Create enhanced prompt for data center expertise
        system_prompt = """You are an expert data center industry analyst and news assistant. Your role is to:

1. Provide accurate, up-to-date information about the data center industry based on the provided articles
2. Cover topics including: construction/expansion projects, M&A activity, technology trends (cooling, power, AI infrastructure), sustainability initiatives, market analysis, and major players (Equinix, Digital Realty, QTS, etc.)
3. Be specific with facts, numbers, and dates when available
4. Cite sources by including the source name and URL for every key claim
5. If articles don't fully answer the question, say so, but still extract any partial facts that *are* present
6. Use industry terminology appropriately (PUE, colocation, hyperscale, edge, interconnection, etc.)

Output rules:
- Prefer a structured answer with headings and bullet points.
- If the user asks for “latest construction projects” (or similar), list each project as its own bullet with: company, location, size/capacity (MW/sqft) if available, status (proposed/planned/under construction), and date.
- Never claim a project detail unless it appears in the provided articles."""
        
        user_prompt = f"""Based on the following recent data center industry articles, please answer this question:

**Question:** {query}

**Available Articles:**
{context_text}

Provide a clear, informative answer based on these sources. Include specific details like company names, locations, capacity (MW), and dates when mentioned. Cite which sources support your answer."""
        
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
            
            # Select model based on provider
            if self.provider == "groq":
                model = "llama-3.1-8b-instant"  # Free, fast model
            elif self.provider == "together":
                model = "meta-llama/Llama-3-8b-chat-hf"  # Free model
            else:
                model = "gpt-3.5-turbo"  # OpenAI model
            
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.4,
                max_tokens=700
            )
            
            answer = response.choices[0].message.content
            
            # Record actual usage (update with actual cost if available)
            if self.cost_tracker and hasattr(response, 'usage'):
                # Update with more accurate cost if usage info is available
                pass  # Cost already recorded in pre-check
            
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
    
    def chat(self, query: str) -> Dict:
        """Main chat method: retrieve context and generate response"""
        # If no articles in database, provide helpful message
        db = SessionLocal()
        try:
            total_articles = db.query(Article).count()
            if total_articles == 0:
                return {
                    'answer': "I don't have any articles in my database yet. The scraper runs every 30 minutes to collect news. Please wait a bit and try again, or ask me a general question about data centers and I'll do my best to help!",
                    'sources': []
                }
        finally:
            db.close()
        
        # Retrieve relevant articles
        articles = self.retrieve_relevant_articles(query, n_results=8)
        
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
                    articles = self.retrieve_relevant_articles(query, n_results=8)
        
        if not articles:
            return {
                'answer': "I couldn't find any articles matching your query. Try asking about data center news, trends, or industry updates. The scraper collects new articles every 30 minutes.",
                'sources': []
            }
        
        # Generate response
        return self.generate_response(query, articles)
