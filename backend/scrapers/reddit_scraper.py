"""
Reddit scraper for data center related subreddits
"""
import praw
from typing import List, Dict, Optional
from datetime import datetime
import logging
import os
from dotenv import load_dotenv
from .base_scraper import BaseScraper

load_dotenv()
logger = logging.getLogger(__name__)

# Subreddits to monitor
SUBREDDITS = ['datacenter', 'sysadmin']

class RedditScraper(BaseScraper):
    """Scraper for Reddit posts"""
    
    def __init__(self):
        super().__init__("Reddit")
        self.reddit = None
        self._init_reddit()
    
    def _init_reddit(self):
        """Initialize Reddit API client"""
        try:
            client_id = os.getenv("REDDIT_CLIENT_ID")
            client_secret = os.getenv("REDDIT_CLIENT_SECRET")
            user_agent = os.getenv("REDDIT_USER_AGENT", "DataCenterNewsBot/1.0")
            
            if client_id and client_secret:
                self.reddit = praw.Reddit(
                    client_id=client_id,
                    client_secret=client_secret,
                    user_agent=user_agent
                )
                self.logger.info("Reddit API initialized successfully")
            else:
                self.logger.warning("Reddit credentials not found. Reddit scraping will be disabled.")
        except Exception as e:
            self.logger.error(f"Error initializing Reddit API: {e}")
    
    def get_source_type(self) -> str:
        return "reddit"
    
    def scrape_subreddit(self, subreddit_name: str, limit: int = 25) -> List[Dict]:
        """Scrape posts from a subreddit"""
        articles = []
        
        if not self.reddit:
            return articles
        
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            
            for submission in subreddit.hot(limit=limit):
                try:
                    # Skip stickied posts and non-text posts
                    if submission.stickied:
                        continue
                    
                    # Get content
                    content = submission.selftext if hasattr(submission, 'selftext') else ""
                    if not content and submission.title:
                        content = submission.title
                    
                    # Parse date
                    published_date = datetime.fromtimestamp(submission.created_utc)
                    
                    article = {
                        'title': submission.title,
                        'content': f"{submission.title}\n\n{content}",
                        'url': f"https://reddit.com{submission.permalink}",
                        'published_date': published_date,
                        'author': str(submission.author) if submission.author else '',
                        'source': f"r/{subreddit_name}",
                        'tags': ', '.join([f"r/{subreddit_name}", "reddit"]) if content else None,
                    }
                    articles.append(article)
                except Exception as e:
                    self.logger.error(f"Error processing Reddit submission: {e}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"Error scraping subreddit r/{subreddit_name}: {e}")
        
        return articles
    
    def scrape(self) -> List[Dict]:
        """Scrape all configured subreddits"""
        all_articles = []
        
        if not self.reddit:
            self.logger.warning("Reddit scraper not available - credentials missing")
            return all_articles
        
        for subreddit_name in SUBREDDITS:
            self.logger.info(f"Scraping subreddit: r/{subreddit_name}")
            articles = self.scrape_subreddit(subreddit_name)
            
            for article in articles:
                normalized = self.normalize_article(article)
                if normalized:
                    all_articles.append(normalized)
            
            self.logger.info(f"Found {len(articles)} posts from r/{subreddit_name}")
        
        return all_articles
