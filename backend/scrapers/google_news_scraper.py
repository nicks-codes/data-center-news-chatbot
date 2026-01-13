"""
Google News scraper for data center news
"""
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import logging
import re
import time
from urllib.parse import quote, urljoin
from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)

# Comprehensive Google News search queries for data center industry
SEARCH_QUERIES = [
    # Core data center terms
    "data center news",
    "data center construction",
    "data center expansion",
    "data center investment",
    
    # Industry segments
    "colocation data center",
    "hyperscale data center",
    "edge data center",
    "wholesale data center",
    "enterprise data center",
    
    # Technology topics
    "data center cooling",
    "data center power",
    "data center PUE efficiency",
    "liquid cooling data center",
    "data center AI infrastructure",
    
    # Business & Market
    "data center REIT",
    "data center acquisition",
    "data center market",
    
    # Major players
    "Equinix data center",
    "Digital Realty",
    "QTS data center",
    "CyrusOne",
    "CoreSite",
    "Vantage Data Centers",
    
    # Sustainability
    "data center sustainability",
    "data center renewable energy",
    "green data center",
    
    # Regional
    "data center Northern Virginia",
    "data center Texas",
    "data center Europe",
    "data center Asia Pacific",
]

class GoogleNewsScraper(BaseScraper):
    """Scraper for Google News with improved parsing and retry logic"""
    
    def __init__(self):
        super().__init__("Google News")
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        self.timeout = 15
        self.max_retries = 2
        # Limit queries to avoid rate limiting - select most important ones
        self.active_queries = SEARCH_QUERIES[:15]  # Use top 15 queries
    
    def get_source_type(self) -> str:
        return "google_news"
    
    def parse_relative_time(self, time_text: str) -> Optional[datetime]:
        """Parse relative time strings like '2 hours ago', '1 day ago'"""
        if not time_text:
            return None
        
        time_text = time_text.lower()
        now = datetime.now()
        
        patterns = [
            (r'(\d+)\s*minute', 'minutes'),
            (r'(\d+)\s*hour', 'hours'),
            (r'(\d+)\s*day', 'days'),
            (r'(\d+)\s*week', 'weeks'),
            (r'(\d+)\s*month', 'months'),
        ]
        
        for pattern, unit in patterns:
            match = re.search(pattern, time_text)
            if match:
                value = int(match.group(1))
                if unit == 'minutes':
                    return now - timedelta(minutes=value)
                elif unit == 'hours':
                    return now - timedelta(hours=value)
                elif unit == 'days':
                    return now - timedelta(days=value)
                elif unit == 'weeks':
                    return now - timedelta(weeks=value)
                elif unit == 'months':
                    return now - timedelta(days=value * 30)
        
        return None
    
    def search_google_news(self, query: str, limit: int = 10) -> List[Dict]:
        """Search Google News for articles with retry logic"""
        articles = []
        
        for attempt in range(self.max_retries):
            try:
                # Use Google News RSS for more reliable parsing
                rss_url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
                
                response = requests.get(rss_url, headers=self.headers, timeout=self.timeout)
                response.raise_for_status()
                
                # Parse as RSS
                import feedparser
                feed = feedparser.parse(response.text)
                
                for entry in feed.entries[:limit]:
                    try:
                        title = entry.title if hasattr(entry, 'title') else ''
                        url = entry.link if hasattr(entry, 'link') else ''
                        
                        if not title or not url:
                            continue
                        
                        # Parse published date
                        published_date = None
                        if hasattr(entry, 'published_parsed') and entry.published_parsed:
                            try:
                                published_date = datetime(*entry.published_parsed[:6])
                            except (TypeError, ValueError):
                                pass
                        
                        if not published_date:
                            published_date = datetime.now()
                        
                        # Get content/summary
                        content = ""
                        if hasattr(entry, 'summary'):
                            # Clean HTML from summary
                            soup = BeautifulSoup(entry.summary, 'html.parser')
                            content = soup.get_text(separator=' ', strip=True)
                        
                        # Extract source from title or content
                        source_name = ""
                        if hasattr(entry, 'source') and hasattr(entry.source, 'title'):
                            source_name = entry.source.title
                        
                        article = {
                            'title': title,
                            'content': f"{title}\n\n{content}" if content else title,
                            'url': url,
                            'published_date': published_date,
                            'author': source_name,
                            'source': f"Google News",
                            'tags': f"google_news, {query}",
                        }
                        articles.append(article)
                    except Exception as e:
                        self.logger.debug(f"Error processing Google News entry: {e}")
                        continue
                
                # Success - break retry loop
                break
                
            except requests.exceptions.Timeout:
                self.logger.warning(f"Timeout searching Google News for '{query}' (attempt {attempt + 1})")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
            except Exception as e:
                self.logger.warning(f"Error searching Google News for '{query}': {e} (attempt {attempt + 1})")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
        
        return articles
    
    def scrape(self) -> List[Dict]:
        """Scrape Google News for all search queries with rate limiting"""
        all_articles = []
        seen_urls = set()  # Deduplicate within this scrape session
        
        for i, query in enumerate(self.active_queries):
            self.logger.info(f"Searching Google News for: {query} ({i+1}/{len(self.active_queries)})")
            articles = self.search_google_news(query, limit=10)
            
            for article in articles:
                # Skip if we've seen this URL before
                url = article.get('url', '')
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                
                normalized = self.normalize_article(article)
                if normalized:
                    all_articles.append(normalized)
            
            self.logger.info(f"Found {len(articles)} articles for '{query}'")
            
            # Rate limiting - be respectful to Google
            if i < len(self.active_queries) - 1:
                time.sleep(2)
        
        self.logger.info(f"Google News scraper found {len(all_articles)} unique articles total")
        return all_articles
