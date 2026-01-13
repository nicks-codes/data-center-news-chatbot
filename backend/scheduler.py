"""
Scheduler for running scrapers continuously
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging
import atexit
from datetime import datetime
import os
import threading

from .scrapers.rss_scraper import RSSScraper
from .scrapers.web_scraper import WebScraper
from .scrapers.reddit_scraper import RedditScraper
from .scrapers.twitter_scraper import TwitterScraper
from .scrapers.google_news_scraper import GoogleNewsScraper
from .database.models import Article
from .database.db import SessionLocal, init_db, canonicalize_url, hash_url
from .services.embedding_service import EmbeddingService
from .services.vector_store import VectorStore
from .utils.relevance import score_and_tag_article

logger = logging.getLogger(__name__)

class ScrapingScheduler:
    """Manages scheduled scraping tasks"""
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.scrapers = [
            RSSScraper(),
            WebScraper(),
            RedditScraper(),
            TwitterScraper(),
            GoogleNewsScraper(),
        ]
        self.embedding_service = EmbeddingService()
        self.vector_store = VectorStore()
        self._run_lock = threading.Lock()
        self._setup_scheduler()
    
    def _setup_scheduler(self):
        """Set up scheduled tasks"""
        interval_minutes = int(os.getenv("SCRAPE_INTERVAL_MINUTES", "30"))
        interval_minutes = max(5, interval_minutes)  # safety floor

        # Run scrapers every N minutes
        self.scheduler.add_job(
            func=self.run_all_scrapers,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id='scrape_articles',
            name='Scrape all news sources',
            replace_existing=True
        )
        
        # Register shutdown handler
        atexit.register(lambda: self.scheduler.shutdown())
    
    def deduplicate_articles(self, articles: list, db) -> list:
        """Remove duplicate articles based on canonical URL hash (and URL fallback)."""
        unique_articles = []
        seen_hashes = set()
        
        for article in articles:
            url = article.get('url', '')
            if not url:
                continue

            canonical_url = canonicalize_url(url)
            url_hash = hash_url(canonical_url)
            article["canonical_url"] = canonical_url
            article["url_hash"] = url_hash

            if url_hash in seen_hashes:
                continue

            # Check if article already exists in database (prefer hash, fallback to URL).
            existing = db.query(Article).filter(
                (Article.url_hash == url_hash) | (Article.url == url) | (Article.canonical_url == canonical_url)
            ).first()
            if not existing:
                unique_articles.append(article)
                seen_hashes.add(url_hash)
        
        return unique_articles
    
    def process_and_store_articles(self, articles: list):
        """Store articles in database and generate embeddings"""
        if not articles:
            return
        
        db = SessionLocal()
        try:
            # Relevance scoring / tagging (helps keep the corpus "data center" focused)
            min_relevance = float(os.getenv("MIN_RELEVANCE_SCORE", "4.0"))
            filtered = []
            for a in articles:
                title = a.get("title", "") or ""
                content = a.get("content", "") or ""
                res = score_and_tag_article(title, content, existing_tags=a.get("tags"))
                a["relevance_score"] = res.score
                a["tags"] = ", ".join(res.tags) if res.tags else a.get("tags")

                # RSS feeds are already curated; keep them even if score is low.
                # Noisy sources (reddit/twitter/web) should clear the threshold.
                source_type = (a.get("source_type") or "").lower()
                if source_type in {"reddit", "twitter", "web"} and res.score < min_relevance:
                    continue
                filtered.append(a)

            # Deduplicate
            unique_articles = self.deduplicate_articles(filtered, db)
            logger.info(
                f"Processing {len(unique_articles)} new articles "
                f"(filtered from {len(articles)}, post-relevance {len(filtered)})"
            )
            
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
                        canonical_url=article_data.get('canonical_url'),
                        url_hash=article_data.get('url_hash'),
                        source=article_data['source'],
                        source_type=article_data['source_type'],
                        published_date=article_data.get('published_date'),
                        author=article_data.get('author'),
                        tags=article_data.get('tags'),
                        relevance_score=article_data.get('relevance_score'),
                        has_embedding=False
                    )
                    db.add(db_article)
                    db_articles.append(db_article)
                except Exception as e:
                    logger.error(f"Error creating article record: {e}")
                    continue
            
            db.commit()
            logger.info(f"Stored {len(db_articles)} articles in database")
            
            # Generate embeddings and store in vector DB (batch for speed)
            if db_articles:
                texts = []
                vector_ids = []
                metadatas = []
                for a in db_articles:
                    texts.append(f"{a.title}\n\n{(a.content or '')[:3000]}")
                    vector_ids.append(f"article_{a.id}")
                    metadatas.append(
                        {
                            "article_id": a.id,
                            "title": a.title,
                            "source": a.source,
                            "url": a.url,
                        }
                    )

                embeddings = self.embedding_service.generate_embeddings_batch(texts)
                batch_ids = []
                batch_embeddings = []
                batch_metadatas = []
                article_by_vid = {}
                for idx, emb in enumerate(embeddings):
                    if not emb:
                        continue
                    vid = vector_ids[idx]
                    batch_ids.append(vid)
                    batch_embeddings.append(emb)
                    batch_metadatas.append(metadatas[idx])
                    article_by_vid[vid] = db_articles[idx]

                if batch_ids and self.vector_store.add_articles_batch(batch_ids, batch_embeddings, batch_metadatas):
                    for vid in batch_ids:
                        a = article_by_vid.get(vid)
                        if not a:
                            continue
                        a.has_embedding = True
                        a.embedding_id = vid
                    db.commit()
                    logger.info(f"Generated embeddings for {len(batch_ids)} articles")
            
        except Exception as e:
            logger.error(f"Error processing articles: {e}")
            db.rollback()
        finally:
            db.close()
    
    def run_all_scrapers(self):
        """Run all scrapers and process results"""
        if not self._run_lock.acquire(blocking=False):
            logger.warning("Previous scrape is still running; skipping this interval.")
            return
        logger.info(f"Starting scheduled scraping at {datetime.now()}")
        all_articles = []
        
        try:
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
        finally:
            self._run_lock.release()
        
        logger.info(f"Completed scraping. Total articles found: {len(all_articles)}")
    
    def start(self):
        """Start the scheduler"""
        init_db()  # Initialize database tables
        self.scheduler.start()
        logger.info("Scraping scheduler started")
        
        # Run initial scrape
        self.run_all_scrapers()
    
    def stop(self):
        """Stop the scheduler"""
        self.scheduler.shutdown()
        logger.info("Scraping scheduler stopped")
