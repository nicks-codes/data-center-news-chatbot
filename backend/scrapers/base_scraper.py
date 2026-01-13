"""
Base scraper class with common functionality
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Set
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
import hashlib
import logging
import os
import re

logger = logging.getLogger(__name__)

# Keywords that indicate data center relevant content
DC_RELEVANCE_KEYWORDS = {
    # Core terms (high weight)
    'high': [
        'data center', 'datacenter', 'data centre',
        'colocation', 'colo facility', 'colo provider',
        'hyperscale', 'hyperscaler',
        'server farm', 'server facility',
        'pue', 'power usage effectiveness',
        'uptime institute', 'tier certification',
    ],
    # Related terms (medium weight)  
    'medium': [
        'edge computing', 'edge data',
        'rack', 'server rack', 'cabinet',
        'ups system', 'uninterruptible power',
        'cooling system', 'liquid cooling', 'immersion cooling',
        'megawatt', 'power capacity',
        'interconnection', 'cross-connect',
        'disaster recovery', 'failover',
        'network infrastructure', 'it infrastructure',
    ],
    # Company/brand terms (medium weight)
    'companies': [
        'equinix', 'digital realty', 'cyrusone', 'qts',
        'coresite', 'vantage', 'stack infrastructure',
        'flexential', 'switch', 'compass datacenters',
        'ntt data', 'iron mountain data',
    ],
    # Technology terms (lower weight - may be general IT)
    'tech': [
        'cloud infrastructure', 'hybrid cloud',
        'virtualization', 'vmware', 'kubernetes',
        'bandwidth', 'latency', 'fiber optic',
        'redundancy', 'high availability',
    ],
}

# Keywords that indicate non-relevant content (filter out)
EXCLUDE_KEYWORDS = [
    'recipe', 'cooking', 'sports score', 'celebrity',
    'horoscope', 'weather forecast', 'lottery',
    'real estate listing', 'apartment for rent',
]


class BaseScraper(ABC):
    """Base class for all scrapers with content relevance filtering"""
    
    def __init__(self, source_name: str):
        self.source_name = source_name
        self.logger = logging.getLogger(f"{__name__}.{source_name}")
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns for efficiency"""
        self.exclude_pattern = re.compile(
            '|'.join(re.escape(kw) for kw in EXCLUDE_KEYWORDS),
            re.IGNORECASE
        )
    
    def generate_article_id(self, url: str, title: str) -> str:
        """Generate a unique ID for an article based on URL and title"""
        content = f"{url}{title}".encode('utf-8')
        return hashlib.md5(content).hexdigest()
    
    def calculate_relevance_score(self, title: str, content: str) -> float:
        """Calculate relevance score for data center content (0-1)"""
        text = f"{title} {content}".lower()
        score = 0.0
        matches = 0
        
        # Check for exclusion keywords first
        if self.exclude_pattern.search(text):
            return 0.0
        
        # High weight keywords (0.4 per match, max 1.0)
        for keyword in DC_RELEVANCE_KEYWORDS['high']:
            if keyword in text:
                score += 0.4
                matches += 1
        
        # Medium weight keywords (0.2 per match)
        for keyword in DC_RELEVANCE_KEYWORDS['medium']:
            if keyword in text:
                score += 0.2
                matches += 1
        
        # Company names (0.3 per match)
        for keyword in DC_RELEVANCE_KEYWORDS['companies']:
            if keyword in text:
                score += 0.3
                matches += 1
        
        # Tech keywords (0.1 per match)
        for keyword in DC_RELEVANCE_KEYWORDS['tech']:
            if keyword in text:
                score += 0.1
                matches += 1
        
        # Normalize score to 0-1 range
        return min(1.0, score)
    
    def is_relevant(self, title: str, content: str, threshold: float = 0.2) -> bool:
        """Check if article is relevant to data centers"""
        return self.calculate_relevance_score(title, content) >= threshold
    
    def clean_text(self, text: str) -> str:
        """Clean text by removing extra whitespace and special characters"""
        if not text:
            return ""
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove null bytes and other control characters
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        return text.strip()
    
    def parse_date(self, date_input) -> Optional[datetime]:
        """Parse date from various formats"""
        if not date_input:
            return None
        
        if isinstance(date_input, datetime):
            return date_input
        
        # Common non-string formats (e.g., time.struct_time tuples)
        if hasattr(date_input, "tm_year") and hasattr(date_input, "tm_mon") and hasattr(date_input, "tm_mday"):
            try:
                return datetime(*date_input[:6])
            except Exception:
                return None
        
        if not isinstance(date_input, str):
            return None
        
        # Common date formats
        formats = [
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
            '%a, %d %b %Y %H:%M:%S %Z',
            '%a, %d %b %Y %H:%M:%S %z',
            '%B %d, %Y',
            '%b %d, %Y',
            '%d %B %Y',
            '%d %b %Y',
            '%m/%d/%Y',
            '%d/%m/%Y',
        ]
        
        date_str = date_input.strip()
        if not date_str:
            return None
        
        # RFC 2822 / RSS-style dates (fast path)
        try:
            dt = parsedate_to_datetime(date_str)
            # `parsedate_to_datetime` can return aware datetimes; downstream code expects naive
            return dt.replace(tzinfo=None) if dt else None
        except Exception:
            pass
        
        # ISO-ish dates
        try:
            iso_str = date_str.replace("Z", "+00:00")
            return datetime.fromisoformat(iso_str).replace(tzinfo=None)
        except Exception:
            pass
        
        # Try common formats with a few cleaned variants
        cleaned_variants = [date_str]
        cleaned_variants.append(re.sub(r'[+-]\d{2}:\d{2}$', '', date_str))  # strip "+00:00"
        cleaned_variants.append(date_str.replace('T', ' ').replace('Z', ''))
        
        for candidate in cleaned_variants:
            for fmt in formats:
                try:
                    return datetime.strptime(candidate, fmt)
                except ValueError:
                    continue
        
        # Try dateutil parser as fallback
        try:
            from dateutil import parser
            return parser.parse(date_input)
        except:
            pass
        
        return None
    
    def normalize_article(self, raw_article: Dict) -> Optional[Dict]:
        """Normalize article data to common format with validation"""
        try:
            title = self.clean_text(raw_article.get('title', ''))
            content = self.clean_text(raw_article.get('content', ''))
            url = raw_article.get('url', '').strip()
            
            # Validate required fields
            if not title or not url:
                return None
            
            # Skip very short content (likely not real articles)
            if len(content) < 50 and len(title) < 20:
                return None
            
            # Apply relevance filtering centrally (can be tuned via env)
            try:
                threshold = float(os.getenv("RELEVANCE_THRESHOLD", "0.2"))
            except ValueError:
                threshold = 0.2
            if not self.is_relevant(title, content, threshold=threshold):
                return None
            
            # Parse published date
            published_date = self.parse_date(raw_article.get('published_date'))
            
            # Skip very old articles (configurable)
            #
            # MAX_ARTICLE_AGE_DAYS:
            # - default: 30
            # - set to 0 to disable age filtering
            max_age_days = 30
            try:
                max_age_days = int(os.getenv("MAX_ARTICLE_AGE_DAYS", "30"))
            except ValueError:
                max_age_days = 30
            if max_age_days < 0:
                max_age_days = 30
            
            if published_date and max_age_days > 0:
                age = datetime.now() - published_date
                if age > timedelta(days=max_age_days):
                    self.logger.debug(f"Skipping old article: {title[:50]}...")
                    return None
            
            article_id = self.generate_article_id(url, title)
            
            # Clean and validate author
            author = self.clean_text(raw_article.get('author', ''))
            if author and len(author) > 200:
                author = author[:200]
            
            # Clean tags
            tags = raw_article.get('tags', '')
            if isinstance(tags, list):
                tags = ', '.join(str(t) for t in tags)
            tags = self.clean_text(tags)
            
            # Use source from article if provided, otherwise use scraper source
            source = raw_article.get('source', '').strip() or self.source_name
            
            normalized = {
                'title': title[:500],  # Limit title length
                'content': content[:10000],  # Limit content length
                'url': url[:1000],  # Limit URL length
                'source': source[:200],
                'source_type': self.get_source_type(),
                'published_date': published_date,
                'author': author or None,
                'tags': tags[:500] if tags else '',
                'article_id': article_id
            }
            
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
