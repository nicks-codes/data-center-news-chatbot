import logging
import time
import random
from typing import Optional, Dict, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from fake_useragent import UserAgent
import trafilatura

logger = logging.getLogger(__name__)

class WebUtils:
    """Utility class for web scraping and content extraction"""
    
    def __init__(self):
        try:
            self.ua = UserAgent()
        except Exception:
            self.ua = None
        self.session = self._create_session()
        
    def _create_session(self) -> requests.Session:
        """Create a requests session with retry logic"""
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def get_headers(self) -> Dict[str, str]:
        """Generate headers with random User-Agent"""
        ua_string = self.ua.random if self.ua else 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        return {
            'User-Agent': ua_string,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }

    def fetch_url(self, url: str, timeout: int = 30) -> Optional[str]:
        """Fetch URL content with error handling and retries"""
        try:
            headers = self.get_headers()
            response = self.session.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching URL {url}: {e}")
            return None

    def extract_article(self, url: str, html: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Extract article content using trafilatura.
        If html is provided, uses it; otherwise fetches the URL.
        """
        if html is None:
            html = self.fetch_url(url)
            
        if not html:
            return None

        try:
            downloaded = html
            
            # Use bare_extraction to get metadata and text
            metadata = trafilatura.bare_extraction(
                downloaded,
                url=url,
                include_comments=False,
                include_tables=False,
                no_fallback=False
            )
            
            if not metadata:
                return None
            
            # Helper to safely get value from dict or object
            def get_val(obj, key):
                if isinstance(obj, dict):
                    return obj.get(key)
                return getattr(obj, key, None)

            # Check if metadata is actually a dictionary
            # In some versions/cases it might be different, but bare_extraction typically returns dict
            # If it failed, it returns None
            
            # If we are here, metadata is not None.
            
            # Defensive coding against unexpected types
            title = get_val(metadata, 'title')
            text = get_val(metadata, 'text')
            
            if not title and not text:
                # If bare_extraction failed to get text, try regular extract
                text = trafilatura.extract(downloaded, url=url)
                if not text:
                    return None
            
            return {
                'title': title,
                'content': text,
                'url': get_val(metadata, 'url') or url,
                'published_date': get_val(metadata, 'date'),
                'author': get_val(metadata, 'author'),
                'sitename': get_val(metadata, 'sitename'),
                'description': get_val(metadata, 'description'),
                'categories': get_val(metadata, 'categories'),
                'tags': get_val(metadata, 'tags'),
            }
            
        except Exception as e:
            logger.error(f"Error extracting article from {url}: {e}")
            # Fallback to simple extraction if everything else fails
            try:
                text = trafilatura.extract(html, url=url)
                if text:
                     return {
                        'title': '', # Can't get title easily without metadata
                        'content': text,
                        'url': url,
                    }
            except:
                pass
            return None
