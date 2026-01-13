"""
Google News scraper for data center news
"""
import concurrent.futures
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import logging
import re
from urllib.parse import quote
from .base_scraper import BaseScraper
from ..utils.web_utils import WebUtils

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
        self.web_utils = WebUtils()
        self.headers = self.web_utils.get_headers()
    
    def get_source_type(self) -> str:
        return "google_news"
    
    def fetch_full_article(self, url: str) -> Optional[str]:
        """Fetch full article content"""
        # Google News URLs are redirects. 
        # We rely on WebUtils (trafilatura/requests) to follow them.
        article_data = self.web_utils.extract_article(url)
        if article_data and article_data.get('content'):
            return article_data['content']
        return None

    def process_article_element(self, element, query: str) -> Optional[Dict]:
        """Process a single Google News article element"""
        try:
            # Find link
            link_tag = element.find('a', href=True)
            if not link_tag:
                return None
            
            # Google News uses relative URLs that need to be converted
            href = link_tag.get('href', '')
            if href.startswith('./'):
                # Convert Google News relative URL to actual URL
                article_id = href.replace('./articles/', '')
                url = f"https://news.google.com/articles/{article_id}"
            else:
                url = href
            
            # Get title
            title_tag = link_tag.find('h3') or link_tag.find('h4')
            if not title_tag:
                # Sometimes title is the link text
                title = link_tag.get_text(strip=True)
            else:
                title = title_tag.get_text(strip=True)
            
            # Get source and time
            source_time = element.find('div', class_=re.compile('source|time', re.I))
            source = ""
            if source_time:
                source = source_time.get_text(strip=True)
            
            # Try to extract date from source text
            published_date = datetime.now()
            if source_time:
                time_text = source_time.get_text()
                # Try to parse relative times like "2 hours ago"
                match = re.search(r'(\d+)\s+(hour|minute|day)', time_text)
                if match:
                    value = int(match.group(1))
                    unit = match.group(2)
                    if unit == 'hour':
                        published_date = datetime.now() - timedelta(hours=value)
                    elif unit == 'minute':
                        published_date = datetime.now() - timedelta(minutes=value)
                    elif unit == 'day':
                        published_date = datetime.now() - timedelta(days=value)
            
            # Get full content if possible
            content = self.fetch_full_article(url)
            
            # Fallback to snippet if full content fails
            if not content:
                snippet_tag = element.find('div', class_=re.compile('snippet|description', re.I))
                content = snippet_tag.get_text(strip=True) if snippet_tag else title
            
            return {
                'title': title,
                'content': content,
                'url': url,
                'published_date': published_date,
                'author': source,
                'source': f"Google News - {query}",
                'tags': f"google_news, {query}",
            }
        except Exception as e:
            self.logger.error(f"Error processing Google News article: {e}")
            return None

    def search_google_news(self, query: str, limit: int = 10) -> List[Dict]:
        """Search Google News for articles"""
        articles = []
        
        try:
            # Google News search URL
            search_url = f"https://news.google.com/search?q={quote(query)}&hl=en&gl=US&ceid=US:en"
            
            # Use web_utils to fetch the search page
            html = self.web_utils.fetch_url(search_url)
            if not html:
                return articles
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find article links (Google News uses specific structure)
            # The structure changes often, but look for article tags
            article_elements = soup.find_all('article', limit=limit)
            
            # Process articles in parallel to fetch full content
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = []
                for element in article_elements:
                    futures.append(executor.submit(self.process_article_element, element, query))
                
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    if result:
                        articles.append(result)
                    
        except Exception as e:
            self.logger.error(f"Error searching Google News for '{query}': {e}")
        
        return articles
    
    def scrape(self) -> List[Dict]:
        """Scrape Google News for all search queries"""
        all_articles = []
        
        for query in SEARCH_QUERIES:
            self.logger.info(f"Searching Google News for: {query}")
            articles = self.search_google_news(query, limit=10) # limit per query
            
            for article in articles:
                normalized = self.normalize_article(article)
                if normalized:
                    all_articles.append(normalized)
            
            self.logger.info(f"Found {len(articles)} articles for '{query}'")
        
        return all_articles
