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
            def _clean_str(value: object) -> str:
                if value is None:
                    return ""
                return str(value).strip()

            def _normalize_tags(value: object) -> Optional[str]:
                """
                Normalize tags into a comma-separated string.
                Accepts None, str, list/tuple/set.
                """
                if value is None:
                    return None
                if isinstance(value, str):
                    tag_str = value.strip()
                    return tag_str or None
                if isinstance(value, (list, tuple, set)):
                    parts = []
                    for item in value:
                        s = _clean_str(item)
                        if s:
                            parts.append(s)
                    if not parts:
                        return None
                    # Deduplicate while preserving order
                    seen = set()
                    deduped = []
                    for p in parts:
                        key = p.lower()
                        if key in seen:
                            continue
                        seen.add(key)
                        deduped.append(p)
                    return ", ".join(deduped)
                # Fallback: stringify
                s = _clean_str(value)
                return s or None

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
            
            # Preserve per-article "source" (site/subreddit/query) if provided.
            # Fall back to the scraper's name if missing.
            source = _clean_str(raw_article.get('source')) or self.source_name

            normalized = {
                'title': _clean_str(raw_article.get('title')),
                'content': _clean_str(raw_article.get('content')),
                'url': _clean_str(raw_article.get('url')),
                'source': source,
                'source_type': self.get_source_type(),
                'published_date': published_date,
                'author': _clean_str(raw_article.get('author')) or None,
                'tags': _normalize_tags(raw_article.get('tags')),
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
