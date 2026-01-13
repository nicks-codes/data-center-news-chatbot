"""
RSS feed scraper for data center news sites
"""
import feedparser
from typing import List, Dict
from datetime import datetime
import logging
import time
import requests
from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)

# RSS feed URLs for data center news sites - comprehensive list
RSS_FEEDS = [
    # Primary Data Center News Sources
    {
        'name': 'Data Center Dynamics',
        'url': 'https://www.datacenterdynamics.com/en/feed/',
        'priority': 1,
    },
    {
        'name': 'Data Center Knowledge',
        'url': 'https://www.datacenterknowledge.com/rss.xml',
        'priority': 1,
    },
    {
        'name': 'Data Center Frontier',
        'url': 'https://www.datacenterfrontier.com/feed/',
        'priority': 1,
    },
    {
        'name': 'Data Center POST',
        'url': 'https://www.datacenterpost.com/feed/',
        'priority': 1,
    },
    # Industry Publications
    {
        'name': 'The Register - Data Centre',
        'url': 'https://www.theregister.com/data_centre/headlines.atom',
        'priority': 2,
    },
    {
        'name': 'TechTarget SearchDataCenter',
        'url': 'https://www.techtarget.com/searchdatacenter/rss',
        'priority': 2,
    },
    {
        'name': 'Network World - Data Center',
        'url': 'https://www.networkworld.com/category/data-center/feed/',
        'priority': 2,
    },
    {
        'name': 'SDxCentral - Data Center',
        'url': 'https://www.sdxcentral.com/data-center/feed/',
        'priority': 2,
    },
    # Cloud & Infrastructure News (often covers data centers)
    {
        'name': 'Ars Technica - IT',
        'url': 'https://feeds.arstechnica.com/arstechnica/technology-lab',
        'priority': 3,
    },
    {
        'name': 'ZDNet - Data Management',
        'url': 'https://www.zdnet.com/topic/data-management/rss.xml',
        'priority': 3,
    },
    {
        'name': 'InfoWorld',
        'url': 'https://www.infoworld.com/index.rss',
        'priority': 3,
    },
    {
        'name': 'The Next Platform',
        'url': 'https://www.nextplatform.com/feed/',
        'priority': 2,
    },
    {
        'name': 'Inside HPC',
        'url': 'https://insidehpc.com/feed/',
        'priority': 2,
    },
    # Business & Investment News (data center deals, expansions)
    {
        'name': 'Reuters Technology',
        'url': 'https://www.reutersagency.com/feed/?taxonomy=best-topics&post_type=best&best-topics=tech',
        'priority': 3,
    },
    # Sustainability & Energy (important for DCs)
    {
        'name': 'GreenBiz',
        'url': 'https://www.greenbiz.com/feed',
        'priority': 3,
    },
    # Vendor/Company Blogs (useful for product news)
    {
        'name': 'Equinix Blog',
        'url': 'https://blog.equinix.com/feed/',
        'priority': 2,
    },
    {
        'name': 'Uptime Institute',
        'url': 'https://uptimeinstitute.com/feed',
        'priority': 1,
    },
]

class RSSScraper(BaseScraper):
    """Scraper for RSS feeds with retry logic and timeout handling"""
    
    def __init__(self):
        super().__init__("RSS Feed")
        self.feeds = RSS_FEEDS
        self.timeout = 15  # seconds
        self.max_retries = 2
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/rss+xml, application/xml, text/xml, */*',
        }
    
    def get_source_type(self) -> str:
        return "rss"
    
    def fetch_feed_content(self, feed_url: str) -> str:
        """Fetch feed content with retry logic"""
        for attempt in range(self.max_retries):
            try:
                response = requests.get(feed_url, headers=self.headers, timeout=self.timeout)
                response.raise_for_status()
                return response.text
            except requests.exceptions.Timeout:
                self.logger.warning(f"Timeout fetching {feed_url} (attempt {attempt + 1})")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"Error fetching {feed_url}: {e} (attempt {attempt + 1})")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
        return None
    
    def clean_html(self, html_content: str) -> str:
        """Remove HTML tags and clean up content"""
        import re
        # Remove HTML tags
        clean = re.sub(r'<[^>]+>', ' ', html_content)
        # Remove extra whitespace
        clean = re.sub(r'\s+', ' ', clean)
        # Remove HTML entities
        clean = re.sub(r'&[a-zA-Z]+;', ' ', clean)
        return clean.strip()
    
    def parse_feed(self, feed_url: str, feed_name: str) -> List[Dict]:
        """Parse a single RSS feed"""
        articles = []
        try:
            # First try fetching with requests for better control
            content = self.fetch_feed_content(feed_url)
            if content:
                feed = feedparser.parse(content)
            else:
                # Fallback to feedparser's built-in fetching
                feed = feedparser.parse(feed_url)
            
            if feed.bozo and feed.bozo_exception:
                # Don't fail completely on parse warnings, just log them
                self.logger.debug(f"Feed parsing warning for {feed_name}: {feed.bozo_exception}")
            
            for entry in feed.entries:
                try:
                    # Parse published date with multiple format support
                    published_date = None
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        try:
                            published_date = datetime(*entry.published_parsed[:6])
                        except (TypeError, ValueError):
                            pass
                    
                    if not published_date and hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                        try:
                            published_date = datetime(*entry.updated_parsed[:6])
                        except (TypeError, ValueError):
                            pass
                    
                    # Get content from various possible fields
                    content = ""
                    if hasattr(entry, 'content') and entry.content:
                        content = entry.content[0].value if isinstance(entry.content, list) else str(entry.content)
                    elif hasattr(entry, 'summary'):
                        content = entry.summary
                    elif hasattr(entry, 'description'):
                        content = entry.description
                    
                    # Clean HTML from content
                    content = self.clean_html(content)
                    
                    # Get tags/categories
                    tags = []
                    if hasattr(entry, 'tags'):
                        tags = [tag.term for tag in entry.tags if hasattr(tag, 'term')]
                    
                    article = {
                        'title': entry.title if hasattr(entry, 'title') else '',
                        'content': content,
                        'url': entry.link if hasattr(entry, 'link') else '',
                        'published_date': published_date,
                        'author': entry.get('author', ''),
                        'source': feed_name,
                        'tags': ', '.join(tags) if tags else '',
                    }
                    
                    # Only add if we have title and URL
                    if article['title'] and article['url']:
                        articles.append(article)
                except Exception as e:
                    self.logger.debug(f"Error parsing entry from {feed_name}: {e}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"Error parsing feed {feed_url}: {e}")
        
        return articles
    
    def scrape(self) -> List[Dict]:
        """Scrape all RSS feeds, sorted by priority"""
        all_articles = []
        
        # Sort feeds by priority (lower is higher priority)
        sorted_feeds = sorted(self.feeds, key=lambda x: x.get('priority', 5))
        
        for feed_config in sorted_feeds:
            self.logger.info(f"Scraping RSS feed: {feed_config['name']}")
            articles = self.parse_feed(feed_config['url'], feed_config['name'])
            
            for article in articles:
                normalized = self.normalize_article(article)
                if normalized:
                    all_articles.append(normalized)
            
            self.logger.info(f"Found {len(articles)} articles from {feed_config['name']}")
            
            # Small delay between feeds to be respectful
            time.sleep(0.5)
        
        return all_articles
