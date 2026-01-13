"""
Twitter scraper for data center related tweets
"""
import tweepy
from typing import List, Dict, Optional
from datetime import datetime
import logging
import os
from dotenv import load_dotenv
from .base_scraper import BaseScraper

load_dotenv()
logger = logging.getLogger(__name__)

# Twitter search terms and accounts
SEARCH_TERMS = [
    "data center",
    "datacenter",
    "colocation",
    "hyperscale",
    "edge computing",
]

class TwitterScraper(BaseScraper):
    """Scraper for Twitter/X posts"""
    
    def __init__(self):
        super().__init__("Twitter")
        self.api = None
        self._init_twitter()
    
    def _init_twitter(self):
        """Initialize Twitter API client"""
        try:
            bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
            api_key = os.getenv("TWITTER_API_KEY")
            api_secret = os.getenv("TWITTER_API_SECRET")
            access_token = os.getenv("TWITTER_ACCESS_TOKEN")
            access_token_secret = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
            
            # Try v2 API first (bearer token)
            if bearer_token:
                self.api = tweepy.Client(bearer_token=bearer_token, wait_on_rate_limit=True)
                self.api_v2 = True
                self.logger.info("Twitter API v2 initialized successfully")
            # Fallback to v1.1 API
            elif api_key and api_secret and access_token and access_token_secret:
                auth = tweepy.OAuthHandler(api_key, api_secret)
                auth.set_access_token(access_token, access_token_secret)
                self.api = tweepy.API(auth, wait_on_rate_limit=True)
                self.api_v2 = False
                self.logger.info("Twitter API v1.1 initialized successfully")
            else:
                self.logger.warning("Twitter credentials not found. Twitter scraping will be disabled.")
        except Exception as e:
            self.logger.error(f"Error initializing Twitter API: {e}")
    
    def get_source_type(self) -> str:
        return "twitter"
    
    def scrape_search(self, query: str, limit: int = 20) -> List[Dict]:
        """Search for tweets matching query"""
        articles = []
        
        if not self.api:
            return articles
        
        try:
            if hasattr(self, 'api_v2') and self.api_v2:
                # Use v2 API
                tweets = self.api.search_recent_tweets(
                    query=query,
                    max_results=min(limit, 100),
                    tweet_fields=['created_at', 'author_id', 'public_metrics']
                )
                
                if tweets.data:
                    for tweet in tweets.data:
                        try:
                            created_at = getattr(tweet, "created_at", None)
                            if isinstance(created_at, datetime):
                                published_date = created_at
                            elif isinstance(created_at, str):
                                published_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                            else:
                                published_date = None
                            
                            article = {
                                'title': tweet.text[:100] + "..." if len(tweet.text) > 100 else tweet.text,
                                'content': tweet.text,
                                'url': f"https://twitter.com/i/web/status/{tweet.id}",
                                'published_date': published_date,
                                'author': f"@{tweet.author_id}" if hasattr(tweet, 'author_id') else '',
                                'source': f"Twitter - {query}",
                                'tags': f"twitter, {query}",
                            }
                            articles.append(article)
                        except Exception as e:
                            self.logger.error(f"Error processing tweet: {e}")
                            continue
            else:
                # Use v1.1 API
                tweets = self.api.search_tweets(q=query, count=limit, lang='en', result_type='recent')
                
                for tweet in tweets:
                    try:
                        published_date = tweet.created_at
                        
                        article = {
                            'title': tweet.text[:100] + "..." if len(tweet.text) > 100 else tweet.text,
                            'content': tweet.text,
                            'url': f"https://twitter.com/{tweet.user.screen_name}/status/{tweet.id}",
                            'published_date': published_date,
                            'author': f"@{tweet.user.screen_name}",
                            'source': f"Twitter - {query}",
                            'tags': f"twitter, {query}",
                        }
                        articles.append(article)
                    except Exception as e:
                        self.logger.error(f"Error processing tweet: {e}")
                        continue
                        
        except Exception as e:
            self.logger.error(f"Error searching Twitter for '{query}': {e}")
        
        return articles
    
    def scrape(self) -> List[Dict]:
        """Scrape tweets from all search terms"""
        all_articles = []
        
        if not self.api:
            self.logger.warning("Twitter scraper not available - credentials missing")
            return all_articles
        
        for search_term in SEARCH_TERMS:
            self.logger.info(f"Searching Twitter for: {search_term}")
            articles = self.scrape_search(search_term, limit=15)
            
            for article in articles:
                normalized = self.normalize_article(article)
                if normalized:
                    all_articles.append(normalized)
            
            self.logger.info(f"Found {len(articles)} tweets for '{search_term}'")
        
        return all_articles
