"""
Reddit scraper for data center related subreddits
"""
import praw
from typing import List, Dict, Optional
from datetime import datetime
import logging
import os
import time
from dotenv import load_dotenv
from .base_scraper import BaseScraper

load_dotenv()
logger = logging.getLogger(__name__)

# Comprehensive list of subreddits related to data centers and infrastructure
SUBREDDITS = [
    # Core data center subreddits
    'datacenter',
    'datacenters',
    
    # IT Infrastructure & Operations
    'sysadmin',
    'networking',
    'homelab',
    'selfhosted',
    
    # Cloud & Virtualization
    'vmware',
    'virtualization',
    'aws',
    'azure',
    'googlecloud',
    
    # Hardware & Servers
    'servers',
    'hardware',
    'homelabsales',
    
    # Networking
    'ccna',
    'ccnp',
    'Ubiquiti',
    
    # Enterprise IT
    'ITCareerQuestions',
    'msp',
]

# Keywords to filter relevant posts
DC_KEYWORDS = [
    'data center', 'datacenter', 'colocation', 'colo',
    'hyperscale', 'edge computing', 'rack', 'server room',
    'ups', 'cooling', 'pdu', 'pue', 'uptime',
    'redundancy', 'failover', 'disaster recovery',
    'network', 'fiber', 'switch', 'router',
]

class RedditScraper(BaseScraper):
    """Scraper for Reddit posts with improved filtering"""
    
    # Core data center subreddits (always scrape everything)
    CORE_SUBREDDITS = ['datacenter', 'datacenters']
    
    def __init__(self):
        super().__init__("Reddit")
        self.reddit = None
        self._init_reddit()
    
    def _init_reddit(self):
        """Initialize Reddit API client"""
        try:
            client_id = os.getenv("REDDIT_CLIENT_ID")
            client_secret = os.getenv("REDDIT_CLIENT_SECRET")
            user_agent = os.getenv("REDDIT_USER_AGENT", "DataCenterNewsBot/2.0 (by /u/datacenterbot)")
            
            if client_id and client_secret:
                self.reddit = praw.Reddit(
                    client_id=client_id,
                    client_secret=client_secret,
                    user_agent=user_agent,
                    check_for_async=False
                )
                self.logger.info("Reddit API initialized successfully")
            else:
                self.logger.warning("Reddit credentials not found. Reddit scraping will be disabled.")
        except Exception as e:
            self.logger.error(f"Error initializing Reddit API: {e}")
    
    def get_source_type(self) -> str:
        return "reddit"
    
    def is_relevant(self, title: str, content: str, subreddit: str) -> bool:
        """Check if a post is relevant to data centers"""
        # Core subreddits are always relevant
        if subreddit.lower() in [s.lower() for s in self.CORE_SUBREDDITS]:
            return True
        
        # For other subreddits, check for keywords
        text = f"{title} {content}".lower()
        return any(keyword in text for keyword in DC_KEYWORDS)
    
    def scrape_subreddit(self, subreddit_name: str, limit: int = 25, filter_relevant: bool = True) -> List[Dict]:
        """Scrape posts from a subreddit"""
        articles = []
        
        if not self.reddit:
            return articles
        
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            
            # Get hot and new posts for better coverage
            submissions = list(subreddit.hot(limit=limit))
            submissions.extend(list(subreddit.new(limit=limit // 2)))
            
            # Deduplicate by ID
            seen_ids = set()
            unique_submissions = []
            for sub in submissions:
                if sub.id not in seen_ids:
                    seen_ids.add(sub.id)
                    unique_submissions.append(sub)
            
            for submission in unique_submissions:
                try:
                    # Skip stickied posts
                    if submission.stickied:
                        continue
                    
                    # Skip very low-score posts (likely spam or low quality)
                    if hasattr(submission, 'score') and submission.score < 0:
                        continue
                    
                    # Get content
                    content = submission.selftext if hasattr(submission, 'selftext') else ""
                    title = submission.title if hasattr(submission, 'title') else ""
                    
                    # Check relevance for non-core subreddits
                    if filter_relevant and not self.is_relevant(title, content, subreddit_name):
                        continue
                    
                    # Parse date
                    published_date = datetime.fromtimestamp(submission.created_utc)
                    
                    # Get flair if available
                    flair = ""
                    if hasattr(submission, 'link_flair_text') and submission.link_flair_text:
                        flair = submission.link_flair_text
                    
                    # Build tags
                    tags = [f"r/{subreddit_name}", "reddit"]
                    if flair:
                        tags.append(flair)
                    
                    article = {
                        'title': title,
                        'content': f"{title}\n\n{content}" if content else title,
                        'url': f"https://reddit.com{submission.permalink}",
                        'published_date': published_date,
                        'author': str(submission.author) if submission.author else '',
                        'source': f"r/{subreddit_name}",
                        'tags': ', '.join(tags),
                    }
                    articles.append(article)
                except Exception as e:
                    self.logger.debug(f"Error processing Reddit submission: {e}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"Error scraping subreddit r/{subreddit_name}: {e}")
        
        return articles
    
    def search_reddit(self, query: str, limit: int = 25) -> List[Dict]:
        """Search Reddit for data center related posts"""
        articles = []
        
        if not self.reddit:
            return articles
        
        try:
            # Search across all of Reddit for the query
            for submission in self.reddit.subreddit("all").search(query, limit=limit, time_filter="week"):
                try:
                    if submission.stickied:
                        continue
                    
                    content = submission.selftext if hasattr(submission, 'selftext') else ""
                    title = submission.title if hasattr(submission, 'title') else ""
                    
                    published_date = datetime.fromtimestamp(submission.created_utc)
                    subreddit_name = str(submission.subreddit)
                    
                    article = {
                        'title': title,
                        'content': f"{title}\n\n{content}" if content else title,
                        'url': f"https://reddit.com{submission.permalink}",
                        'published_date': published_date,
                        'author': str(submission.author) if submission.author else '',
                        'source': f"r/{subreddit_name}",
                        'tags': f"r/{subreddit_name}, reddit, search:{query}",
                    }
                    articles.append(article)
                except Exception as e:
                    self.logger.debug(f"Error processing search result: {e}")
                    continue
        except Exception as e:
            self.logger.error(f"Error searching Reddit for '{query}': {e}")
        
        return articles
    
    def scrape(self) -> List[Dict]:
        """Scrape all configured subreddits"""
        all_articles = []
        
        if not self.reddit:
            self.logger.warning("Reddit scraper not available - credentials missing")
            return all_articles
        
        # First, scrape core data center subreddits (no filtering)
        for subreddit_name in self.CORE_SUBREDDITS:
            self.logger.info(f"Scraping core subreddit: r/{subreddit_name}")
            articles = self.scrape_subreddit(subreddit_name, limit=50, filter_relevant=False)
            
            for article in articles:
                normalized = self.normalize_article(article)
                if normalized:
                    all_articles.append(normalized)
            
            self.logger.info(f"Found {len(articles)} posts from r/{subreddit_name}")
            time.sleep(0.5)  # Rate limiting
        
        # Then, scrape related subreddits with filtering
        related_subs = [s for s in SUBREDDITS if s.lower() not in [c.lower() for c in self.CORE_SUBREDDITS]]
        for subreddit_name in related_subs[:10]:  # Limit to first 10 to avoid rate limits
            self.logger.info(f"Scraping related subreddit: r/{subreddit_name}")
            articles = self.scrape_subreddit(subreddit_name, limit=25, filter_relevant=True)
            
            for article in articles:
                normalized = self.normalize_article(article)
                if normalized:
                    all_articles.append(normalized)
            
            self.logger.info(f"Found {len(articles)} relevant posts from r/{subreddit_name}")
            time.sleep(0.5)  # Rate limiting
        
        # Search for data center topics across Reddit
        search_queries = ["data center news", "datacenter infrastructure", "colocation"]
        for query in search_queries:
            self.logger.info(f"Searching Reddit for: {query}")
            articles = self.search_reddit(query, limit=15)
            
            for article in articles:
                normalized = self.normalize_article(article)
                if normalized:
                    all_articles.append(normalized)
            
            self.logger.info(f"Found {len(articles)} posts for search '{query}'")
            time.sleep(1)  # Rate limiting for search
        
        self.logger.info(f"Reddit scraper found {len(all_articles)} total articles")
        return all_articles
