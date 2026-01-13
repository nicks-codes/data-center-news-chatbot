"""
Web scraper for sites without RSS feeds
"""
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime
import logging
import re
from urllib.parse import urljoin, urlparse
from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)

# Web scraping configurations
WEB_SOURCES = [
    {
        'name': 'Global Data Center Hub',
        'base_url': 'https://www.globaldatacenterhub.com',
        'article_links': ['https://www.globaldatacenterhub.com/news'],
    },
    {
        'name': 'Semi Analysis',
        'base_url': 'https://www.semianalysis.com',
        'article_links': ['https://www.semianalysis.com'],
    },
    {
        'name': 'Uptime Institute Blog',
        'base_url': 'https://uptimeinstitute.com',
        'article_links': ['https://uptimeinstitute.com/blog'],
    },
    {
        'name': 'Bisnow',
        'base_url': 'https://www.bisnow.com',
        'article_links': ['https://www.bisnow.com/data-center'],
    },
    {
        'name': 'TechRepublic',
        'base_url': 'https://www.techrepublic.com',
        'article_links': ['https://www.techrepublic.com/topic/data-center/'],
    },
    {
        'name': 'Data Center Watch',
        'base_url': 'https://www.datacenterwatch.com',
        'article_links': ['https://www.datacenterwatch.com'],
    },
]

class WebScraper(BaseScraper):
    """Scraper for web pages"""
    
    def __init__(self):
        super().__init__("Web Scraper")
        self.sources = WEB_SOURCES
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    def get_source_type(self) -> str:
        return "web"
    
    def extract_text(self, soup: BeautifulSoup) -> str:
        """Extract main text content from a page"""
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header", "aside"]):
            script.decompose()
        
        # Try to find main content area
        main_content = soup.find('main') or soup.find('article') or soup.find('div', class_=re.compile('content|article|post', re.I))
        
        if main_content:
            text = main_content.get_text(separator=' ', strip=True)
        else:
            text = soup.get_text(separator=' ', strip=True)
        
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        return text[:5000]  # Limit content length
    
    def extract_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        """Extract published date from page"""
        # Try various date selectors
        date_selectors = [
            {'tag': 'time', 'attr': 'datetime'},
            {'tag': 'meta', 'attr': 'property', 'value': 'article:published_time'},
            {'tag': 'meta', 'attr': 'name', 'value': 'publish-date'},
            {'tag': 'meta', 'attr': 'name', 'value': 'date'},
        ]
        
        for selector in date_selectors:
            if selector['tag'] == 'time':
                time_tag = soup.find('time')
                if time_tag and selector['attr'] in time_tag.attrs:
                    try:
                        return datetime.fromisoformat(time_tag[selector['attr']].replace('Z', '+00:00'))
                    except:
                        pass
            elif selector['tag'] == 'meta':
                meta = soup.find('meta', {selector['attr']: selector.get('value', '')})
                if meta and 'content' in meta.attrs:
                    try:
                        return datetime.fromisoformat(meta['content'].replace('Z', '+00:00'))
                    except:
                        pass
        
        return None
    
    def scrape_article(self, url: str, source_name: str) -> Optional[Dict]:
        """Scrape a single article page"""
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract title
            title = ""
            if soup.title:
                title = soup.title.string.strip()
            else:
                h1 = soup.find('h1')
                if h1:
                    title = h1.get_text(strip=True)
            
            # Extract content
            content = self.extract_text(soup)
            
            # Extract date
            published_date = self.extract_date(soup)
            
            # Extract author
            author = ""
            author_tag = soup.find('meta', {'name': 'author'}) or soup.find('span', class_=re.compile('author', re.I))
            if author_tag:
                if hasattr(author_tag, 'get'):
                    author = author_tag.get('content', '') or author_tag.get_text(strip=True)
            
            if not title or not content:
                return None
            
            return {
                'title': title,
                'content': content,
                'url': url,
                'published_date': published_date,
                'author': author,
                'source': source_name,
            }
        except Exception as e:
            self.logger.error(f"Error scraping article {url}: {e}")
            return None
    
    def find_article_links(self, url: str, source_name: str) -> List[str]:
        """Find article links on a listing page"""
        article_links = []
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find links that look like articles
            links = soup.find_all('a', href=True)
            for link in links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                # Filter for article-like links
                if any(keyword in href.lower() or keyword in text.lower() 
                      for keyword in ['article', 'news', 'post', 'blog', 'story']):
                    full_url = urljoin(url, href)
                    if urlparse(full_url).netloc == urlparse(url).netloc:
                        article_links.append(full_url)
            
            # Limit to avoid too many requests
            return list(set(article_links))[:20]
        except Exception as e:
            self.logger.error(f"Error finding article links on {url}: {e}")
            return []
    
    def scrape(self) -> List[Dict]:
        """Scrape all web sources"""
        all_articles = []
        
        for source_config in self.sources:
            self.logger.info(f"Scraping web source: {source_config['name']}")
            
            for listing_url in source_config['article_links']:
                article_links = self.find_article_links(listing_url, source_config['name'])
                
                for article_url in article_links[:10]:  # Limit per source
                    article = self.scrape_article(article_url, source_config['name'])
                    if article:
                        normalized = self.normalize_article(article)
                        if normalized:
                            all_articles.append(normalized)
                    
                    # Be respectful with rate limiting
                    import time
                    time.sleep(1)
            
            self.logger.info(f"Scraped articles from {source_config['name']}")
        
        return all_articles
