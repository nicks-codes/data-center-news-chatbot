"""
Web scraper for sites without RSS feeds
"""
import concurrent.futures
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Optional
import logging
from bs4 import BeautifulSoup

from .base_scraper import BaseScraper
from ..utils.web_utils import WebUtils

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
        self.web_utils = WebUtils()
    
    def get_source_type(self) -> str:
        return "web"
    
    def scrape_article(self, url: str, source_name: str) -> Optional[Dict]:
        """Scrape a single article page using WebUtils"""
        try:
            article_data = self.web_utils.extract_article(url)
            
            if not article_data:
                return None
            
            # Add source name if not present
            article_data['source'] = source_name
            
            return article_data
        except Exception as e:
            self.logger.error(f"Error scraping article {url}: {e}")
            return None
    
    def find_article_links(self, url: str, source_name: str) -> List[str]:
        """Find article links on a listing page"""
        article_links = []
        try:
            html = self.web_utils.fetch_url(url)
            if not html:
                return []
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find links that look like articles
            links = soup.find_all('a', href=True)
            for link in links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                # Check for Substack style links (/p/)
                if '/p/' in href:
                     full_url = urljoin(url, href)
                     if urlparse(full_url).netloc == urlparse(url).netloc:
                         article_links.append(full_url)
                         continue
                
                # Filter for article-like links
                # Broaden keywords slightly but keep relevant
                if any(keyword in href.lower() or keyword in text.lower() 
                      for keyword in ['article', 'news', 'post', 'blog', 'story', 'report', 'analysis']):
                    full_url = urljoin(url, href)
                    if urlparse(full_url).netloc == urlparse(url).netloc:
                        article_links.append(full_url)
            
            # Deduplicate locally
            unique_links = list(set(article_links))
            self.logger.info(f"Found {len(unique_links)} potential articles on {url}")
            return unique_links[:20]  # Limit to 20 most recent/relevant
        except Exception as e:
            self.logger.error(f"Error finding article links on {url}: {e}")
            return []
    
    def _process_source(self, source_config: Dict) -> List[Dict]:
        """Process a single source (find links and scrape articles)"""
        source_articles = []
        self.logger.info(f"Scraping web source: {source_config['name']}")
        
        all_links = []
        for listing_url in source_config['article_links']:
            links = self.find_article_links(listing_url, source_config['name'])
            all_links.extend(links)
        
        # Remove duplicates
        all_links = list(set(all_links))
        
        # Scrape articles in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            # Create a dictionary to map futures to URLs for error reporting
            future_to_url = {
                executor.submit(self.scrape_article, url, source_config['name']): url 
                for url in all_links[:10]  # Limit per source
            }
            
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    article = future.result()
                    if article:
                        normalized = self.normalize_article(article)
                        if normalized:
                            source_articles.append(normalized)
                except Exception as e:
                    self.logger.error(f"Error processing {url}: {e}")
                    
        self.logger.info(f"Scraped {len(source_articles)} articles from {source_config['name']}")
        return source_articles

    def scrape(self) -> List[Dict]:
        """Scrape all web sources"""
        all_articles = []
        
        # Process sources sequentially to be polite, but articles within source in parallel
        for source_config in self.sources:
            articles = self._process_source(source_config)
            all_articles.extend(articles)
        
        return all_articles
