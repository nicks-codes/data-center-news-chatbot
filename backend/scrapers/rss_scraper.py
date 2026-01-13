"""
RSS feed scraper for data center news sites
"""
import concurrent.futures
import feedparser
from typing import List, Dict, Optional
from datetime import datetime
import logging
from .base_scraper import BaseScraper
from ..utils.web_utils import WebUtils

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
        self.web_utils = WebUtils()
    
    def get_source_type(self) -> str:
        return "rss"
    
    def fetch_full_content(self, url: str) -> Optional[str]:
        """Fetch full content of an article"""
        article_data = self.web_utils.extract_article(url)
        if article_data and article_data.get('content'):
            return article_data['content']
        return None

    def process_entry(self, entry, feed_name: str) -> Optional[Dict]:
        """Process a single RSS entry"""
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
            
            # If content is short, try to fetch full article
            if len(content) < 500 and hasattr(entry, 'link'):
                full_content = self.fetch_full_content(entry.link)
                if full_content:
                    content = full_content
            
            # Skip if still no content
            if not content:
                return None

            return {
                'title': entry.title,
                'content': content,
                'url': entry.link,
                'published_date': published_date,
                'author': entry.get('author', ''),
                'source': feed_name,
            }
        except Exception as e:
            self.logger.error(f"Error parsing entry from {feed_name}: {e}")
            return None

    def parse_feed(self, feed_url: str, feed_name: str) -> List[Dict]:
        """Parse a single RSS feed"""
        articles = []
        try:
            feed = feedparser.parse(feed_url)
            
            if feed.bozo and feed.bozo_exception:
                self.logger.warning(f"Feed parsing error for {feed_name}: {feed.bozo_exception}")
                # Don't return empty list immediately, try to process what we have if any
            
            # Process entries in parallel
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = []
                for entry in feed.entries[:20]: # Limit to 20 recent items
                    futures.append(executor.submit(self.process_entry, entry, feed_name))
                
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    if result:
                        articles.append(result)
                    
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
