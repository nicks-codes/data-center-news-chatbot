"""
Scheduler for running scrapers continuously
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging
import atexit
from datetime import datetime

from .scrapers.rss_scraper import RSSScraper
from .scrapers.web_scraper import WebScraper
from .scrapers.reddit_scraper import RedditScraper
from .scrapers.twitter_scraper import TwitterScraper
from .scrapers.google_news_scraper import GoogleNewsScraper
from .database.models import Article
from .database.db import SessionLocal, init_db
from .services.embedding_service import EmbeddingService
from .services.vector_store import VectorStore

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
        self._setup_scheduler()
    
    def _setup_scheduler(self):
        """Set up scheduled tasks"""
        # Run scrapers every 30 minutes
        self.scheduler.add_job(
            func=self.run_all_scrapers,
            trigger=IntervalTrigger(minutes=30),
            id='scrape_articles',
            name='Scrape all news sources',
            replace_existing=True
        )
        
        # Register shutdown handler
        atexit.register(lambda: self.scheduler.shutdown())
    
    def deduplicate_articles(self, articles: list, db) -> list:
        """Remove duplicate articles based on URL"""
        unique_articles = []
        seen_urls = set()
        
        for article in articles:
            url = article.get('url', '')
            if url and url not in seen_urls:
                # Check if article already exists in database
                existing = db.query(Article).filter(Article.url == url).first()
                if not existing:
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
            
            # Generate embeddings and store in vector DB
            articles_to_embed = []
            for db_article in db_articles:
                # Create embedding text (title + content)
                embedding_text = f"{db_article.title}\n\n{db_article.content[:3000]}"
                embedding = self.embedding_service.generate_embedding(embedding_text)
                
                if embedding:
                    # Use article ID from database
                    vector_id = f"article_{db_article.id}"
                    
                    metadata = {
                        'article_id': db_article.id,
                        'title': db_article.title,
                        'source': db_article.source,
                        'url': db_article.url,
                    }
                    
                    if self.vector_store.add_article(vector_id, embedding, metadata):
                        db_article.has_embedding = True
                        db_article.embedding_id = vector_id
                        articles_to_embed.append(db_article)
            
            if articles_to_embed:
                db.commit()
                logger.info(f"Generated embeddings for {len(articles_to_embed)} articles")
            
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
