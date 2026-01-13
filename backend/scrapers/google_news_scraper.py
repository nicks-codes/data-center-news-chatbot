"""
Google News scraper for data center news
"""
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime
import logging
import re
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
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    def get_source_type(self) -> str:
        return "google_news"
    
    def search_google_news(self, query: str, limit: int = 20) -> List[Dict]:
        """Search Google News for articles"""
        articles = []
        
        try:
            # Google News search URL
            search_url = f"https://news.google.com/search?q={quote(query)}&hl=en&gl=US&ceid=US:en"
            
            response = requests.get(search_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find article links (Google News uses specific structure)
            article_elements = soup.find_all('article', limit=limit)
            
            for element in article_elements:
                try:
                    # Find link
                    link_tag = element.find('a', href=True)
                    if not link_tag:
                        continue
                    
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
                        continue
                    title = title_tag.get_text(strip=True)
                    
                    # Get source and time
                    source_time = element.find('div', class_=re.compile('source|time', re.I))
                    source = ""
                    if source_time:
                        source = source_time.get_text(strip=True)
                    
                    # Try to extract date from source text
                    published_date = None
                    if source_time:
                        time_text = source_time.get_text()
                        # Try to parse relative times like "2 hours ago"
                        # For simplicity, use current time minus estimated hours
                        match = re.search(r'(\d+)\s+(hour|minute)', time_text)
                        if match:
                            from datetime import timedelta
                            value = int(match.group(1))
                            unit = match.group(2)
                            if unit == 'hour':
                                published_date = datetime.now() - timedelta(hours=value)
                            elif unit == 'minute':
                                published_date = datetime.now() - timedelta(minutes=value)
                    
                    if not published_date:
                        published_date = datetime.now()
                    
                    # Get snippet/description
                    snippet_tag = element.find('div', class_=re.compile('snippet|description', re.I))
                    content = snippet_tag.get_text(strip=True) if snippet_tag else title
                    
                    article = {
                        'title': title,
                        'content': f"{title}\n\n{content}",
                        'url': url,
                        'published_date': published_date,
                        'author': source,
                        'source': f"Google News - {query}",
                        'tags': f"google_news, {query}",
                    }
                    articles.append(article)
                except Exception as e:
                    self.logger.error(f"Error processing Google News article: {e}")
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
