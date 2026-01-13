"""
RSS feed scraper for data center news sites
"""
import feedparser
from typing import List, Dict
from datetime import datetime
import logging
from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)

# RSS feed URLs for data center news sites
RSS_FEEDS = [
    {
        'name': 'Data Center Dynamics',
        'url': 'https://www.datacenterdynamics.com/en/feed/',
    },
    {
        'name': 'Data Center Knowledge',
        'url': 'https://www.datacenterknowledge.com/rss.xml',
    },
    {
        'name': 'Data Center Frontier',
        'url': 'https://www.datacenterfrontier.com/feed/',
    },
    {
        'name': 'TechTarget IT Infrastructure',
        'url': 'https://www.techtarget.com/searchdatacenter/rss',
    },
    {
        'name': 'Data Center POST',
        'url': 'https://www.datacenterpost.com/feed/',
    },
    {
        'name': 'The Register',
        'url': 'https://www.theregister.com/data_centre/headlines.atom',
    },
]

class RSSScraper(BaseScraper):
    """Scraper for RSS feeds"""
    
    def __init__(self):
        super().__init__("RSS Feed")
        self.feeds = RSS_FEEDS
    
    def get_source_type(self) -> str:
        return "rss"
    
    def parse_feed(self, feed_url: str, feed_name: str) -> List[Dict]:
        """Parse a single RSS feed"""
        articles = []
        try:
            feed = feedparser.parse(feed_url)
            
            if feed.bozo and feed.bozo_exception:
                self.logger.warning(f"Feed parsing error for {feed_name}: {feed.bozo_exception}")
                return articles
            
            for entry in feed.entries:
                try:
                    # Parse published date
                    published_date = None
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        published_date = datetime(*entry.published_parsed[:6])
                    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                        published_date = datetime(*entry.updated_parsed[:6])
                    
                    # Get content
                    content = ""
                    if hasattr(entry, 'content'):
                        content = entry.content[0].value if entry.content else ""
                    elif hasattr(entry, 'summary'):
                        content = entry.summary
                    elif hasattr(entry, 'description'):
                        content = entry.description
                    
                    article = {
                        'title': entry.title,
                        'content': content,
                        'url': entry.link,
                        'published_date': published_date,
                        'author': entry.get('author', ''),
                        'source': feed_name,
                    }
                    articles.append(article)
                except Exception as e:
                    self.logger.error(f"Error parsing entry from {feed_name}: {e}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"Error parsing feed {feed_url}: {e}")
        
        return articles
    
    def scrape(self) -> List[Dict]:
        """Scrape all RSS feeds"""
        all_articles = []
        
        for feed_config in self.feeds:
            self.logger.info(f"Scraping RSS feed: {feed_config['name']}")
            articles = self.parse_feed(feed_config['url'], feed_config['name'])
            
            for article in articles:
                normalized = self.normalize_article(article)
                if normalized:
                    all_articles.append(normalized)
            
            self.logger.info(f"Found {len(articles)} articles from {feed_config['name']}")
        
        return all_articles
