"""
RAG-based chat service for answering questions about data center news
"""
import openai
import os
from typing import List, Dict, Optional
import logging
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
            # Try semantic search first (if embeddings available)
            query_embedding = self.embedding_service.generate_embedding(query)
            if query_embedding:
                # Search vector store
                similar_articles = self.vector_store.search_similar(query_embedding, n_results=n_results)
                
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
                            'published_date': article.published_date.isoformat() if article.published_date else None,
                        })
            
            # Fallback to keyword search if no semantic results
            if not articles:
                # Simple keyword search in title and content
                query_lower = query.lower()
                query_words = query_lower.split()
                
                all_articles = db.query(Article).order_by(Article.published_date.desc()).limit(50).all()
                
                for article in all_articles:
                    title_lower = article.title.lower() if article.title else ""
                    content_lower = article.content.lower() if article.content else ""
                    
                    # Score based on keyword matches
                    score = 0
                    for word in query_words:
                        if word in title_lower:
                            score += 3  # Title matches are more important
                        if word in content_lower:
                            score += 1
                    
                    if score > 0:
                        articles.append({
                            'title': article.title,
                            'content': article.content[:1000],  # Limit content
                            'url': article.url,
                            'source': article.source,
                            'published_date': article.published_date.isoformat() if article.published_date else None,
                            'score': score
                        })
                
                # Sort by score and take top results
                articles.sort(key=lambda x: x.get('score', 0), reverse=True)
                articles = articles[:n_results]
                
                # Remove score before returning
                for article in articles:
                    article.pop('score', None)
        finally:
            db.close()
        
        return articles
    
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
            context_text += f"Content: {article['content'][:500]}...\n"  # Limit content length
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
4. Cite sources by mentioning the publication name
5. If articles don't fully answer the question, say so and share what relevant information is available
6. Use industry terminology appropriately (PUE, colocation, hyperscale, edge, interconnection, etc.)

Keep responses informative but concise. Focus on the most relevant and recent information."""
        
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
                temperature=0.7,
                max_tokens=500
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
        articles = self.retrieve_relevant_articles(query, n_results=5)
        
        if not articles:
            return {
                'answer': "I couldn't find any articles matching your query. Try asking about data center news, trends, or industry updates. The scraper collects new articles every 30 minutes.",
                'sources': []
            }
        
        # Generate response
        return self.generate_response(query, articles)
