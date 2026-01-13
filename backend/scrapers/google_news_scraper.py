"""
Google News scraper for data center news
"""
import feedparser
from typing import List, Dict
from datetime import datetime
import logging
from urllib.parse import quote
from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)

# Google News search queries
SEARCH_QUERIES = [
    "data center news",
    "datacenter industry",
    "colocation data center",
    "hyperscale data center",
    "edge data center",
]

class GoogleNewsScraper(BaseScraper):
    """Scraper for Google News"""
    
    def __init__(self):
        super().__init__("Google News")
    
    def get_source_type(self) -> str:
        return "google_news"
    
    def search_google_news(self, query: str, limit: int = 20) -> List[Dict]:
        """
        Search Google News using its RSS endpoint (more stable than HTML scraping).
        """
        articles = []
        
        try:
            rss_url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
            feed = feedparser.parse(rss_url)

            if feed.bozo and getattr(feed, "bozo_exception", None):
                self.logger.warning(f"Google News RSS parsing error for '{query}': {feed.bozo_exception}")
                return articles

            for entry in feed.entries[:limit]:
                try:
                    published_date = None
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        published_date = datetime(*entry.published_parsed[:6])
                    elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                        published_date = datetime(*entry.updated_parsed[:6])
                    else:
                        published_date = datetime.now()

                    title = getattr(entry, "title", "").strip()
                    url = getattr(entry, "link", "").strip()

                    # Google News RSS typically provides a short summary/snippet
                    summary = ""
                    if hasattr(entry, "summary"):
                        summary = entry.summary
                    elif hasattr(entry, "description"):
                        summary = entry.description

                    article = {
                        "title": title,
                        "content": f"{title}\n\n{summary}".strip(),
                        "url": url,
                        "published_date": published_date,
                        "author": getattr(entry, "source", {}).get("title", "") if hasattr(entry, "source") else "",
                        "source": f"Google News - {query}",
                        "tags": ["google_news", query],
                    }
                    articles.append(article)
                except Exception as e:
                    self.logger.error(f"Error processing Google News RSS entry: {e}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"Error searching Google News for '{query}': {e}")
        
        return articles
    
    def scrape(self) -> List[Dict]:
        """Scrape Google News for all search queries"""
        all_articles = []
        
        for query in SEARCH_QUERIES:
            self.logger.info(f"Searching Google News for: {query}")
            articles = self.search_google_news(query, limit=15)
            
            for article in articles:
                normalized = self.normalize_article(article)
                if normalized:
                    all_articles.append(normalized)
            
            self.logger.info(f"Found {len(articles)} articles for '{query}'")
        
        return all_articles
