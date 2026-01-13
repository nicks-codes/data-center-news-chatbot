"""
Web scraper for sites without RSS feeds
"""
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime
import logging
import re
import time
from urllib.parse import urljoin, urlparse
from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)

# Comprehensive web scraping configurations for data center news
WEB_SOURCES = [
    # Primary Data Center News Sites
    {
        'name': 'Uptime Institute Blog',
        'base_url': 'https://uptimeinstitute.com',
        'article_links': ['https://uptimeinstitute.com/resources/blog'],
        'article_selector': 'a[href*="/blog/"]',
        'priority': 1,
    },
    {
        'name': 'Bisnow Data Center',
        'base_url': 'https://www.bisnow.com',
        'article_links': ['https://www.bisnow.com/national/data-center'],
        'article_selector': 'a[href*="/news/"]',
        'priority': 1,
    },
    {
        'name': 'Baxtel News',
        'base_url': 'https://baxtel.com',
        'article_links': ['https://baxtel.com/news'],
        'article_selector': 'a[href^="/news/"]',
        'priority': 1,
    },
    # Industry Analysis
    {
        'name': 'Semi Analysis',
        'base_url': 'https://www.semianalysis.com',
        'article_links': ['https://www.semianalysis.com'],
        'article_selector': 'a[href*="/p/"]',
        'priority': 2,
    },
    # Technology & Infrastructure News
    {
        'name': 'Capacity Media',
        'base_url': 'https://www.capacitymedia.com',
        'article_links': ['https://www.capacitymedia.com/data-centres'],
        'article_selector': 'a[href*="/article/"]',
        'priority': 2,
    },
    {
        'name': 'Telecom Ramblings',
        'base_url': 'https://www.telecomramblings.com',
        'article_links': ['https://www.telecomramblings.com/category/data-centers/'],
        'article_selector': 'a[href*="/20"]',  # Year-based URLs
        'priority': 2,
    },
    # Business & Real Estate
    {
        'name': 'Commercial Observer - Data Centers',
        'base_url': 'https://commercialobserver.com',
        'article_links': ['https://commercialobserver.com/tag/data-centers/'],
        'article_selector': 'a[href*="/20"]',
        'priority': 3,
    },
    # Regional/International
    {
        'name': 'Data Economy',
        'base_url': 'https://data-economy.com',
        'article_links': ['https://data-economy.com/category/data-centres/'],
        'article_selector': 'a[href*="/20"]',
        'priority': 2,
    },
    # Tech Analysis
    {
        'name': 'Blocks and Files',
        'base_url': 'https://blocksandfiles.com',
        'article_links': ['https://blocksandfiles.com'],
        'article_selector': 'a[href*="/20"]',
        'priority': 3,
    },
]

# Data center relevance keywords for filtering
DC_KEYWORDS = [
    'data center', 'datacenter', 'data centre', 
    'colocation', 'colo', 'hyperscale',
    'edge computing', 'server', 'rack',
    'cooling', 'pue', 'uptime',
    'equinix', 'digital realty', 'qts', 'coresite',
    'aws', 'azure', 'google cloud', 'gcp',
    'power', 'megawatt', 'mw',
]

class WebScraper(BaseScraper):
    """Scraper for web pages with improved content extraction and retry logic"""
    
    def __init__(self):
        super().__init__("Web Scraper")
        self.sources = WEB_SOURCES
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
    
    def get_source_type(self) -> str:
        return "web"
    
    def fetch_page(self, url: str) -> Optional[str]:
        """Fetch page content with retry logic"""
        for attempt in range(self.max_retries):
            try:
                response = requests.get(url, headers=self.headers, timeout=self.timeout)
                response.raise_for_status()
                return response.text
            except requests.exceptions.Timeout:
                self.logger.warning(f"Timeout fetching {url} (attempt {attempt + 1})")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"Error fetching {url}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
        return None
    
    def is_relevant(self, title: str, content: str) -> bool:
        """Check if article is relevant to data centers"""
        text = f"{title} {content}".lower()
        return any(keyword in text for keyword in DC_KEYWORDS)
    
    def extract_text(self, soup: BeautifulSoup) -> str:
        """Extract main text content from a page"""
        # Remove unwanted elements
        for element in soup(["script", "style", "nav", "footer", "header", "aside", 
                            "advertisement", "sidebar", "menu", "noscript", "iframe"]):
            element.decompose()
        
        # Also remove common ad/tracking elements by class
        for element in soup.find_all(class_=re.compile(r'(ad|advertisement|tracking|sidebar|menu|nav|footer|header|comment)', re.I)):
            element.decompose()
        
        # Try to find main content area in order of specificity
        content_selectors = [
            ('article', {}),
            ('main', {}),
            ('div', {'class': re.compile(r'(article|post|content|entry|story)[-_]?(body|content|text)?', re.I)}),
            ('div', {'id': re.compile(r'(article|post|content|entry|story)', re.I)}),
            ('div', {'class': re.compile(r'(prose|text|body)', re.I)}),
        ]
        
        main_content = None
        for tag, attrs in content_selectors:
            main_content = soup.find(tag, attrs)
            if main_content:
                break
        
        if main_content:
            # Get paragraphs for cleaner text
            paragraphs = main_content.find_all('p')
            if paragraphs:
                text = ' '.join(p.get_text(strip=True) for p in paragraphs)
            else:
                text = main_content.get_text(separator=' ', strip=True)
        else:
            # Fallback to body text
            body = soup.find('body')
            text = body.get_text(separator=' ', strip=True) if body else soup.get_text(separator=' ', strip=True)
        
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove common boilerplate phrases
        boilerplate = [
            r'cookie policy', r'privacy policy', r'terms of service',
            r'subscribe to our newsletter', r'sign up for',
            r'all rights reserved', r'©.*?\d{4}',
        ]
        for pattern in boilerplate:
            text = re.sub(pattern, '', text, flags=re.I)
        
        return text[:8000].strip()  # Limit content length
    
    def extract_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        """Extract published date from page with multiple strategies"""
        # Try structured data first
        date_selectors = [
            {'tag': 'time', 'attr': 'datetime'},
            {'tag': 'meta', 'attrs': {'property': 'article:published_time'}},
            {'tag': 'meta', 'attrs': {'name': 'publish-date'}},
            {'tag': 'meta', 'attrs': {'name': 'date'}},
            {'tag': 'meta', 'attrs': {'name': 'DC.date'}},
            {'tag': 'meta', 'attrs': {'itemprop': 'datePublished'}},
        ]
        
        for selector in date_selectors:
            try:
                if 'attrs' in selector:
                    element = soup.find(selector['tag'], selector['attrs'])
                else:
                    element = soup.find(selector['tag'])
                
                if element:
                    date_str = element.get('datetime') or element.get('content') or element.get_text()
                    if date_str:
                        # Try various date formats
                        for fmt in [
                            '%Y-%m-%dT%H:%M:%S',
                            '%Y-%m-%dT%H:%M:%SZ',
                            '%Y-%m-%dT%H:%M:%S%z',
                            '%Y-%m-%d',
                            '%B %d, %Y',
                            '%b %d, %Y',
                            '%d %B %Y',
                            '%d %b %Y',
                        ]:
                            try:
                                # Handle timezone offset
                                clean_date = re.sub(r'\+\d{2}:\d{2}$', '', date_str.strip())
                                clean_date = clean_date.replace('Z', '')
                                return datetime.strptime(clean_date[:19], fmt[:19] if 'T' in fmt else fmt)
                            except ValueError:
                                continue
                        
                        # Try fromisoformat as fallback
                        try:
                            return datetime.fromisoformat(date_str.replace('Z', '+00:00').replace('+00:00', ''))
                        except:
                            pass
            except Exception:
                continue
        
        # Look for date patterns in visible text
        date_patterns = [
            r'(\w+ \d{1,2}, \d{4})',  # January 15, 2024
            r'(\d{1,2} \w+ \d{4})',    # 15 January 2024
            r'(\d{4}-\d{2}-\d{2})',    # 2024-01-15
        ]
        
        text = soup.get_text()[:2000]  # Look in first part of page
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    from dateutil import parser
                    return parser.parse(match.group(1))
                except:
                    pass
        
        return None
    
    def extract_author(self, soup: BeautifulSoup) -> str:
        """Extract author from page"""
        author_selectors = [
            {'tag': 'meta', 'attrs': {'name': 'author'}},
            {'tag': 'meta', 'attrs': {'property': 'article:author'}},
            {'tag': 'a', 'attrs': {'rel': 'author'}},
            {'tag': 'span', 'attrs': {'class': re.compile(r'author', re.I)}},
            {'tag': 'div', 'attrs': {'class': re.compile(r'author', re.I)}},
            {'tag': 'p', 'attrs': {'class': re.compile(r'(author|byline)', re.I)}},
        ]
        
        for selector in author_selectors:
            try:
                element = soup.find(selector['tag'], selector.get('attrs', {}))
                if element:
                    author = element.get('content') or element.get_text(strip=True)
                    if author and len(author) < 100:  # Sanity check
                        # Clean up common prefixes
                        author = re.sub(r'^(by|author:)\s*', '', author, flags=re.I)
                        return author.strip()
            except Exception:
                continue
        
        return ""
    
    def scrape_article(self, url: str, source_name: str) -> Optional[Dict]:
        """Scrape a single article page"""
        content = self.fetch_page(url)
        if not content:
            return None
        
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # Extract title - prefer og:title, then h1, then title tag
            title = ""
            og_title = soup.find('meta', {'property': 'og:title'})
            if og_title and og_title.get('content'):
                title = og_title['content'].strip()
            
            if not title:
                h1 = soup.find('h1')
                if h1:
                    title = h1.get_text(strip=True)
            
            if not title and soup.title:
                title = soup.title.string.strip() if soup.title.string else ""
            
            # Clean up title - remove site name suffix
            title = re.sub(r'\s*[\|–-]\s*[^|–-]+$', '', title).strip()
            
            # Extract content
            article_content = self.extract_text(soup)
            
            # Extract date
            published_date = self.extract_date(soup)
            
            # Extract author
            author = self.extract_author(soup)
            
            # Extract description for additional context
            description = ""
            og_desc = soup.find('meta', {'property': 'og:description'}) or soup.find('meta', {'name': 'description'})
            if og_desc and og_desc.get('content'):
                description = og_desc['content'].strip()
            
            if not title or not article_content:
                return None
            
            # Combine content with description if content is short
            if len(article_content) < 200 and description:
                article_content = f"{description}\n\n{article_content}"
            
            return {
                'title': title,
                'content': article_content,
                'url': url,
                'published_date': published_date,
                'author': author,
                'source': source_name,
            }
        except Exception as e:
            self.logger.error(f"Error parsing article {url}: {e}")
            return None
    
    def find_article_links(self, url: str, source_config: Dict) -> List[str]:
        """Find article links on a listing page"""
        article_links = []
        content = self.fetch_page(url)
        if not content:
            return []
        
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # Use custom selector if provided
            custom_selector = source_config.get('article_selector')
            if custom_selector:
                links = soup.select(custom_selector)
            else:
                links = soup.find_all('a', href=True)
            
            base_netloc = urlparse(url).netloc
            
            for link in links:
                href = link.get('href', '')
                if not href or href.startswith('#') or href.startswith('javascript:'):
                    continue
                
                # Build full URL
                full_url = urljoin(url, href)
                parsed = urlparse(full_url)
                
                # Only include links from same domain
                if parsed.netloc != base_netloc:
                    continue
                
                # Filter out common non-article pages
                skip_patterns = [
                    '/tag/', '/category/', '/author/', '/page/',
                    '/search', '/login', '/register', '/contact',
                    '/about', '/privacy', '/terms', '/cookie',
                    '.pdf', '.jpg', '.png', '.gif',
                ]
                if any(pattern in full_url.lower() for pattern in skip_patterns):
                    continue
                
                # Look for article-like URL patterns
                article_patterns = [
                    r'/\d{4}/',  # Year in URL
                    r'/article/',
                    r'/news/',
                    r'/post/',
                    r'/blog/',
                    r'/story/',
                    r'/p/',  # Substack style
                ]
                
                if any(re.search(pattern, full_url.lower()) for pattern in article_patterns):
                    article_links.append(full_url)
            
            # Deduplicate and limit
            return list(dict.fromkeys(article_links))[:15]
        except Exception as e:
            self.logger.error(f"Error finding article links on {url}: {e}")
            return []
    
    def scrape(self) -> List[Dict]:
        """Scrape all web sources with priority ordering"""
        all_articles = []
        
        # Sort by priority
        sorted_sources = sorted(self.sources, key=lambda x: x.get('priority', 5))
        
        for source_config in sorted_sources:
            source_name = source_config['name']
            self.logger.info(f"Scraping web source: {source_name}")
            source_articles = 0
            
            for listing_url in source_config['article_links']:
                article_links = self.find_article_links(listing_url, source_config)
                self.logger.info(f"Found {len(article_links)} potential articles from {source_name}")
                
                for article_url in article_links[:8]:  # Limit per listing page
                    article = self.scrape_article(article_url, source_name)
                    if article:
                        normalized = self.normalize_article(article)
                        if normalized:
                            all_articles.append(normalized)
                            source_articles += 1
                    
                    # Rate limiting
                    time.sleep(1.5)
            
            self.logger.info(f"Scraped {source_articles} relevant articles from {source_name}")
            time.sleep(1)  # Delay between sources
        
        self.logger.info(f"Web scraper found {len(all_articles)} total articles")
        return all_articles
