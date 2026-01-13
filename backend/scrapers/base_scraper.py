"""
Base scraper class with common functionality
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from datetime import datetime
import hashlib
import logging

logger = logging.getLogger(__name__)

class BaseScraper(ABC):
    """Base class for all scrapers"""
    
    def __init__(self, source_name: str):
        self.source_name = source_name
        self.logger = logging.getLogger(f"{__name__}.{source_name}")
    
    def generate_article_id(self, url: str, title: str) -> str:
        """Generate a unique ID for an article based on URL and title"""
        content = f"{url}{title}".encode('utf-8')
        return hashlib.md5(content).hexdigest()
    
    def normalize_article(self, raw_article: Dict) -> Optional[Dict]:
        """Normalize article data to common format"""
        try:
            # Parse published date
            published_date = None
            if raw_article.get('published_date'):
                if isinstance(raw_article['published_date'], str):
                    # Try to parse various date formats
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%a, %d %b %Y %H:%M:%S %Z']:
                        try:
                            published_date = datetime.strptime(raw_article['published_date'], fmt)
                            break
                        except ValueError:
                            continue
                elif isinstance(raw_article['published_date'], datetime):
                    published_date = raw_article['published_date']
            
            article_id = self.generate_article_id(
                raw_article.get('url', ''),
                raw_article.get('title', '')
            )
            
            normalized = {
                'title': (raw_article.get('title') or '').strip(),
                'content': (raw_article.get('content') or '').strip(),
                'url': (raw_article.get('url') or '').strip(),
                'source': self.source_name,
                'source_type': self.get_source_type(),
                'published_date': published_date,
                'author': (raw_article.get('author') or '').strip() or None,
                'tags': raw_article.get('tags', ''),
                'article_id': article_id
            }
            
            # Validate required fields
            if not normalized['title'] or not normalized['url']:
                return None
                
            return normalized
        except Exception as e:
            self.logger.error(f"Error normalizing article: {e}")
            return None
    
    @abstractmethod
    def get_source_type(self) -> str:
        """Return the source type (rss, web, reddit, twitter, google_news)"""
        pass
    
    @abstractmethod
    def scrape(self) -> List[Dict]:
        """Scrape articles and return list of normalized articles"""
        pass
