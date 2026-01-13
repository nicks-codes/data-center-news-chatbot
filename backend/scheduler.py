"""
Scheduler for running scrapers continuously with improved error handling
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging
import atexit
import os
from datetime import datetime

from .scrapers.rss_scraper import RSSScraper
from .scrapers.web_scraper import WebScraper
from .scrapers.reddit_scraper import RedditScraper
from .scrapers.twitter_scraper import TwitterScraper
from .scrapers.google_news_scraper import GoogleNewsScraper
from .scrapers.base_scraper import BaseScraper
from .database.models import Article
from .database.db import SessionLocal, init_db
from .services.embedding_service import EmbeddingService
from .services.vector_store import VectorStore
from .services.text_chunker import chunk_text

logger = logging.getLogger(__name__)

# Scraping interval in minutes (configurable via environment)
SCRAPE_INTERVAL = int(os.getenv("SCRAPE_INTERVAL_MINUTES", "30"))

# Relevance threshold for filtering articles
RELEVANCE_THRESHOLD = float(os.getenv("RELEVANCE_THRESHOLD", "0.2"))


class ScrapingScheduler:
    """Manages scheduled scraping tasks with improved error handling and filtering"""
    
    def __init__(self):
        self.scheduler = BackgroundScheduler(
            job_defaults={
                'coalesce': True,  # Combine missed runs
                'max_instances': 1,  # Only one instance at a time
                'misfire_grace_time': 60 * 15,  # 15 min grace period
            }
        )
        self.scrapers = [
            RSSScraper(),  # Primary source - most reliable
            GoogleNewsScraper(),  # Good coverage
            WebScraper(),  # Supplementary
            RedditScraper(),  # Community discussions
            TwitterScraper(),  # Real-time updates
        ]
        self.embedding_service = EmbeddingService()
        self.vector_store = VectorStore()
        self.is_running = False
        self._setup_scheduler()
    
    def _setup_scheduler(self):
        """Set up scheduled tasks"""
        # Run scrapers at configured interval
        self.scheduler.add_job(
            func=self.run_all_scrapers,
            trigger=IntervalTrigger(minutes=SCRAPE_INTERVAL),
            id='scrape_articles',
            name='Scrape all news sources',
            replace_existing=True
        )
        
        # Run cleanup job daily
        self.scheduler.add_job(
            func=self.cleanup_old_articles,
            trigger=IntervalTrigger(hours=24),
            id='cleanup_articles',
            name='Clean up old articles',
            replace_existing=True
        )
        
        # Register shutdown handler
        atexit.register(self._shutdown)
    
    def deduplicate_articles(self, articles: list, db) -> list:
        """Remove duplicate articles based on URL"""
        if not articles:
            return []
        
        # Collect candidate URLs and fetch existing URLs in one query (much faster than N queries)
        urls = [a.get('url', '') for a in articles if a.get('url')]
        existing_urls = set()
        if urls:
            try:
                existing_urls = {row[0] for row in db.query(Article.url).filter(Article.url.in_(urls)).all()}
            except Exception as e:
                logger.warning(f"Could not prefetch existing URLs for dedupe: {e}")
                existing_urls = set()
        
        unique_articles = []
        seen_urls = set()
        for article in articles:
            url = article.get('url', '')
            if not url:
                continue
            if url in seen_urls or url in existing_urls:
                continue
            unique_articles.append(article)
            seen_urls.add(url)
        
        return unique_articles
    
    def process_and_store_articles(self, articles: list):
        """Store articles in database and generate embeddings"""
        if not articles:
            return
        
        db = SessionLocal()
        try:
            # Deduplicate
            unique_articles = self.deduplicate_articles(articles, db)
            logger.info(f"Processing {len(unique_articles)} new articles (filtered from {len(articles)})")
            
            if not unique_articles:
                return
            
            # Store in database
            db_articles = []
            for article_data in unique_articles:
                try:
                    db_article = Article(
                        title=article_data['title'],
                        content=article_data['content'],
                        url=article_data['url'],
                        source=article_data['source'],
                        source_type=article_data['source_type'],
                        published_date=article_data.get('published_date'),
                        author=article_data.get('author'),
                        tags=article_data.get('tags'),
                        has_embedding=False
                    )
                    db.add(db_article)
                    db_articles.append(db_article)
                except Exception as e:
                    logger.error(f"Error creating article record: {e}")
                    continue
            
            db.commit()
            logger.info(f"Stored {len(db_articles)} articles in database")
            
            # Generate embeddings and store in vector DB (chunked for better retrieval)
            if getattr(self.embedding_service, "enabled", False) and getattr(self.vector_store, "collection", None) is not None:
                max_chunks = int(os.getenv("MAX_EMBED_CHUNKS_PER_ARTICLE", "8") or "8")
                chunk_size = int(os.getenv("EMBED_CHUNK_MAX_CHARS", "1200") or "1200")
                chunk_overlap = int(os.getenv("EMBED_CHUNK_OVERLAP_CHARS", "200") or "200")

                vector_ids = []
                texts = []
                metadatas = []
                documents = []

                for db_article in db_articles:
                    base_text = f"{db_article.title}\n\n{(db_article.content or '')}"
                    chunks = chunk_text(
                        base_text,
                        max_chars=chunk_size,
                        overlap_chars=chunk_overlap,
                        max_chunks=max_chunks,
                    )
                    if not chunks:
                        continue

                    published_iso = db_article.published_date.isoformat() if db_article.published_date else None
                    for idx, ch in enumerate(chunks):
                        vector_ids.append(f"article_{db_article.id}_chunk_{idx}")
                        texts.append(ch)
                        documents.append(ch)
                        metadatas.append({
                            "article_id": db_article.id,
                            "chunk_index": idx,
                            "chunk_total": len(chunks),
                            "title": db_article.title,
                            "source": db_article.source,
                            "source_type": db_article.source_type,
                            "url": db_article.url,
                            "published_date": published_iso,
                        })

                if vector_ids:
                    embeddings = self.embedding_service.generate_embeddings_batch(texts)
                    # Filter out failures to keep batch lengths aligned
                    ok_ids = []
                    ok_embs = []
                    ok_metas = []
                    ok_docs = []
                    for vid, emb, meta, doc in zip(vector_ids, embeddings, metadatas, documents):
                        if emb:
                            ok_ids.append(vid)
                            ok_embs.append(emb)
                            ok_metas.append(meta)
                            ok_docs.append(doc)

                    if ok_ids and self.vector_store.add_articles_batch(ok_ids, ok_embs, ok_metas, documents=ok_docs):
                        # Mark each DB article as embedded if at least one chunk was stored
                        embedded_article_ids = {m["article_id"] for m in ok_metas if "article_id" in m}
                        embedded_count = 0
                        for db_article in db_articles:
                            if db_article.id in embedded_article_ids:
                                db_article.has_embedding = True
                                db_article.embedding_id = f"article_{db_article.id}"
                                embedded_count += 1
                        db.commit()
                        logger.info(f"Generated chunked embeddings for {embedded_count} articles")
            
        except Exception as e:
            logger.error(f"Error processing articles: {e}")
            db.rollback()
        finally:
            db.close()
    
    def run_all_scrapers(self):
        """Run all scrapers and process results"""
        logger.info(f"Starting scheduled scraping at {datetime.now()}")
        all_articles = []
        
        for scraper in self.scrapers:
            try:
                logger.info(f"Running scraper: {scraper.source_name}")
                articles = scraper.scrape()
                all_articles.extend(articles)
                logger.info(f"Scraper {scraper.source_name} found {len(articles)} articles")
            except Exception as e:
                logger.error(f"Error running scraper {scraper.source_name}: {e}")
        
        # Process and store all articles
        if all_articles:
            self.process_and_store_articles(all_articles)
        
        logger.info(f"Completed scraping. Total articles found: {len(all_articles)}")
    
    def cleanup_old_articles(self):
        """Remove articles older than 90 days to keep database manageable"""
        from datetime import timedelta
        
        db = SessionLocal()
        try:
            cutoff_date = datetime.now() - timedelta(days=90)
            
            # Get old articles
            old_articles = db.query(Article).filter(
                Article.scraped_date < cutoff_date
            ).all()
            
            if not old_articles:
                logger.info("No old articles to clean up")
                return
            
            # Remove from vector store
            for article in old_articles:
                if article.id:
                    try:
                        self.vector_store.delete_by_article_id(article.id)
                    except Exception as e:
                        logger.warning(f"Could not delete embedding for article {article.id}: {e}")
            
            # Delete from database
            deleted_count = db.query(Article).filter(
                Article.scraped_date < cutoff_date
            ).delete()
            
            db.commit()
            logger.info(f"Cleaned up {deleted_count} articles older than 90 days")
            
        except Exception as e:
            logger.error(f"Error cleaning up old articles: {e}")
            db.rollback()
        finally:
            db.close()
    
    def _shutdown(self):
        """Graceful shutdown handler"""
        try:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=False)
                logger.info("Scheduler shutdown complete")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    def start(self):
        """Start the scheduler"""
        if self.is_running:
            logger.warning("Scheduler is already running")
            return
        
        init_db()  # Initialize database tables
        self.scheduler.start()
        self.is_running = True
        logger.info(f"Scraping scheduler started (interval: {SCRAPE_INTERVAL} minutes)")
        
        # Run initial scrape in background
        import threading
        thread = threading.Thread(target=self.run_all_scrapers, daemon=True)
        thread.start()
    
    def stop(self):
        """Stop the scheduler"""
        if not self.is_running:
            return
        
        self.scheduler.shutdown(wait=False)
        self.is_running = False
        logger.info("Scraping scheduler stopped")
