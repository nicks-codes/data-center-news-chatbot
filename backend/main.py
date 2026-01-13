"""
FastAPI application for Data Center News Chatbot
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import os
import logging
from contextlib import asynccontextmanager

from .services.chat_service import ChatService
from .scheduler import ScrapingScheduler

# Load .env early to ensure all services can access it
from pathlib import Path
from dotenv import load_dotenv

env_paths = [
    Path(__file__).parent / ".env",  # Backend folder (preferred)
    Path.cwd() / ".env",
    Path(__file__).parent.parent / ".env",
]
for env_path in env_paths:
    if env_path.exists():
        load_dotenv(env_path, override=True)
        break
else:
    load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown"""
    global scheduler
    # Startup
    logger.info("Starting Data Center News Chatbot...")
    scheduler = ScrapingScheduler()
    scheduler.start()
    logger.info("Scheduler started")
    yield
    # Shutdown
    logger.info("Shutting down...")
    if scheduler:
        scheduler.stop()

app = FastAPI(
    title="Data Center News Chatbot",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize chat service
chat_service = ChatService()

# Mount static files - check multiple locations
frontend_paths = [
    os.path.join(os.path.dirname(__file__), "..", "frontend"),  # c:\frontend
    "frontend",
    os.path.join(os.path.dirname(__file__), "frontend"),
]
for frontend_path in frontend_paths:
    if os.path.exists(frontend_path):
        app.mount("/static", StaticFiles(directory=frontend_path), name="static")
        logger.info(f"Serving static files from: {frontend_path}")
        break

# Also serve CSS and JS files directly
@app.get("/styles.css")
async def get_styles():
    """Serve CSS file"""
    css_paths = [
        os.path.join(os.path.dirname(__file__), "..", "frontend", "styles.css"),
        "frontend/styles.css",
    ]
    for css_path in css_paths:
        if os.path.exists(css_path):
            return FileResponse(css_path, media_type="text/css")
    return {"error": "CSS file not found"}

@app.get("/app.js")
async def get_js():
    """Serve JavaScript file"""
    js_paths = [
        os.path.join(os.path.dirname(__file__), "..", "frontend", "app.js"),
        "frontend/app.js",
    ]
    for js_path in js_paths:
        if os.path.exists(js_path):
            return FileResponse(js_path, media_type="application/javascript")
    return {"error": "JS file not found"}

# Request/Response models
class ChatRequest(BaseModel):
    query: str

class ChatResponse(BaseModel):
    answer: str
    sources: list

@app.get("/")
async def root():
    """Serve the frontend"""
    frontend_paths = [
        os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html"),
        "frontend/index.html",
        os.path.join(os.path.dirname(__file__), "frontend", "index.html"),
    ]
    for frontend_path in frontend_paths:
        if os.path.exists(frontend_path):
            return FileResponse(frontend_path)
    return {"message": "Data Center News Chatbot API - Frontend not found. Please ensure frontend folder exists."}

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Chat endpoint for asking questions"""
    try:
        if not request.query or not request.query.strip():
            raise HTTPException(status_code=400, detail="Query cannot be empty")
        
        result = chat_service.chat(request.query.strip())
        return ChatResponse(**result)
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stats")
async def get_stats():
    """Get statistics about the knowledge base and costs"""
    try:
        from .database.db import SessionLocal
        from .database.models import Article
        from .services.vector_store import VectorStore
        from .services.cost_tracker import CostTracker
        from sqlalchemy import func
        import os
        
        db = SessionLocal()
        try:
            total_articles = db.query(Article).count()
            articles_with_embeddings = db.query(Article).filter(Article.has_embedding == True).count()
            
            # Get source breakdown
            source_counts = db.query(
                Article.source_type, 
                func.count(Article.id)
            ).group_by(Article.source_type).all()
            sources = {source: count for source, count in source_counts}
            
            # Get recent articles count (last 24 hours)
            from datetime import datetime, timedelta
            recent_count = db.query(Article).filter(
                Article.scraped_date >= datetime.now() - timedelta(hours=24)
            ).count()
            
            vector_store = VectorStore()
            vector_count = vector_store.get_collection_size()
            
            # Check if using free services
            ai_provider = os.getenv("AI_PROVIDER", "").lower()
            embedding_provider = os.getenv("EMBEDDING_PROVIDER", "").lower()
            is_free = (ai_provider in ["groq", "together"] and 
                      embedding_provider == "sentence-transformers")
            
            # Get cost statistics only if using paid services
            cost_stats = None
            if not is_free:
                cost_tracker = CostTracker()
                cost_stats = cost_tracker.get_current_stats()
            
            return {
                "total_articles": total_articles,
                "articles_with_embeddings": articles_with_embeddings,
                "vector_store_size": vector_count,
                "recent_articles_24h": recent_count,
                "sources": sources,
                "cost_stats": cost_stats,
                "is_free": is_free,
                "ai_provider": ai_provider,
                "embedding_provider": embedding_provider,
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/scrape")
async def trigger_scrape():
    """Manually trigger a scraping run"""
    global scheduler
    try:
        if scheduler:
            # Run in background thread to not block
            import threading
            thread = threading.Thread(target=scheduler.run_all_scrapers)
            thread.start()
            return {"status": "started", "message": "Scraping started in background"}
        else:
            return {"status": "error", "message": "Scheduler not initialized"}
    except Exception as e:
        logger.error(f"Error triggering scrape: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/articles")
async def get_articles(
    limit: int = 20,
    offset: int = 0,
    source_type: Optional[str] = None,
    search: Optional[str] = None
):
    """Get recent articles with optional filtering"""
    try:
        from .database.db import SessionLocal
        from .database.models import Article
        
        db = SessionLocal()
        try:
            query = db.query(Article).order_by(Article.published_date.desc())
            
            if source_type:
                query = query.filter(Article.source_type == source_type)
            
            if search:
                search_term = f"%{search}%"
                query = query.filter(
                    (Article.title.ilike(search_term)) | 
                    (Article.content.ilike(search_term))
                )
            
            total = query.count()
            articles = query.offset(offset).limit(limit).all()
            
            return {
                "total": total,
                "offset": offset,
                "limit": limit,
                "articles": [
                    {
                        "id": a.id,
                        "title": a.title,
                        "url": a.url,
                        "source": a.source,
                        "source_type": a.source_type,
                        "published_date": a.published_date.isoformat() if a.published_date else None,
                        "scraped_date": a.scraped_date.isoformat() if a.scraped_date else None,
                        "has_embedding": a.has_embedding,
                    }
                    for a in articles
                ]
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error getting articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/articles/{article_id}")
async def get_article(article_id: int):
    """Get a specific article by ID"""
    try:
        from .database.db import SessionLocal
        from .database.models import Article
        
        db = SessionLocal()
        try:
            article = db.query(Article).filter(Article.id == article_id).first()
            if not article:
                raise HTTPException(status_code=404, detail="Article not found")
            
            return {
                "id": article.id,
                "title": article.title,
                "content": article.content,
                "url": article.url,
                "source": article.source,
                "source_type": article.source_type,
                "published_date": article.published_date.isoformat() if article.published_date else None,
                "scraped_date": article.scraped_date.isoformat() if article.scraped_date else None,
                "author": article.author,
                "tags": article.tags,
                "has_embedding": article.has_embedding,
            }
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting article: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
