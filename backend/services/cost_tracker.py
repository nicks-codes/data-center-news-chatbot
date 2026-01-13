"""
Cost tracking service to monitor API usage and prevent unexpected spending
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class CostTracker:
    """Tracks API usage and estimates costs"""
    
    # OpenAI pricing (as of 2024, update if needed)
    EMBEDDING_COST_PER_1K_TOKENS = 0.00002  # text-embedding-3-small
    CHAT_COST_PER_1K_TOKENS = 0.0015  # gpt-3.5-turbo (input)
    CHAT_OUTPUT_COST_PER_1K_TOKENS = 0.002  # gpt-3.5-turbo (output)
    
    # Daily/monthly limits (in USD)
    DAILY_LIMIT = float(os.getenv("DAILY_COST_LIMIT", "5.0"))  # $5/day default
    MONTHLY_LIMIT = float(os.getenv("MONTHLY_COST_LIMIT", "50.0"))  # $50/month default
    
    def __init__(self):
        self.stats_file = Path("cost_stats.json")
        self.stats = self._load_stats()
        self._check_limits()
    
    def _load_stats(self) -> Dict:
        """Load usage statistics from file"""
        if self.stats_file.exists():
            try:
                with open(self.stats_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading cost stats: {e}")
        
        # Initialize default stats
        return {
            'daily': {},
            'monthly': {},
            'total_embeddings': 0,
            'total_chat_requests': 0,
            'total_cost': 0.0
        }
    
    def _save_stats(self):
        """Save usage statistics to file"""
        try:
            with open(self.stats_file, 'w') as f:
                json.dump(self.stats, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving cost stats: {e}")
    
    def _get_date_key(self) -> str:
        """Get current date as string key"""
        return datetime.now().strftime("%Y-%m-%d")
    
    def _get_month_key(self) -> str:
        """Get current month as string key"""
        return datetime.now().strftime("%Y-%m")
    
    def _check_limits(self):
        """Check if we've exceeded daily/monthly limits"""
        today = self._get_date_key()
        this_month = self._get_month_key()
        
        daily_cost = self.stats['daily'].get(today, 0.0)
        monthly_cost = sum(self.stats['monthly'].values())
        
        if daily_cost >= self.DAILY_LIMIT:
            logger.warning(f"⚠️ DAILY COST LIMIT REACHED: ${daily_cost:.2f} / ${self.DAILY_LIMIT}")
            return False
        
        if monthly_cost >= self.MONTHLY_LIMIT:
            logger.warning(f"⚠️ MONTHLY COST LIMIT REACHED: ${monthly_cost:.2f} / ${self.MONTHLY_LIMIT}")
            return False
        
        return True
    
    def estimate_embedding_cost(self, text: str) -> float:
        """Estimate cost for embedding generation"""
        # Rough estimate: 1 token ≈ 4 characters
        estimated_tokens = len(text) / 4
        cost = (estimated_tokens / 1000) * self.EMBEDDING_COST_PER_1K_TOKENS
        return cost
    
    def estimate_chat_cost(self, input_text: str, output_text: str = "") -> float:
        """Estimate cost for chat completion"""
        input_tokens = len(input_text) / 4
        output_tokens = len(output_text) / 4 if output_text else 500  # Estimate if not provided
        
        input_cost = (input_tokens / 1000) * self.CHAT_COST_PER_1K_TOKENS
        output_cost = (output_tokens / 1000) * self.CHAT_OUTPUT_COST_PER_1K_TOKENS
        
        return input_cost + output_cost
    
    def record_embedding(self, text: str, actual_cost: Optional[float] = None):
        """Record an embedding operation"""
        if not self._check_limits():
            raise Exception("Cost limit exceeded. Operation blocked.")
        
        cost = actual_cost or self.estimate_embedding_cost(text)
        today = self._get_date_key()
        this_month = self._get_month_key()
        
        # Update stats
        if today not in self.stats['daily']:
            self.stats['daily'][today] = 0.0
        if this_month not in self.stats['monthly']:
            self.stats['monthly'][this_month] = 0.0
        
        self.stats['daily'][today] += cost
        self.stats['monthly'][this_month] += cost
        self.stats['total_embeddings'] += 1
        self.stats['total_cost'] += cost
        
        self._save_stats()
        
        logger.info(f"Embedding cost: ${cost:.4f} | Daily: ${self.stats['daily'][today]:.2f} | Monthly: ${self.stats['monthly'][this_month]:.2f}")
    
    def record_chat(self, input_text: str, output_text: str = "", actual_cost: Optional[float] = None):
        """Record a chat operation"""
        if not self._check_limits():
            raise Exception("Cost limit exceeded. Operation blocked.")
        
        cost = actual_cost or self.estimate_chat_cost(input_text, output_text)
        today = self._get_date_key()
        this_month = self._get_month_key()
        
        # Update stats
        if today not in self.stats['daily']:
            self.stats['daily'][today] = 0.0
        if this_month not in self.stats['monthly']:
            self.stats['monthly'][this_month] = 0.0
        
        self.stats['daily'][today] += cost
        self.stats['monthly'][this_month] += cost
        self.stats['total_chat_requests'] += 1
        self.stats['total_cost'] += cost
        
        self._save_stats()
        
        logger.info(f"Chat cost: ${cost:.4f} | Daily: ${self.stats['daily'][today]:.2f} | Monthly: ${self.stats['monthly'][this_month]:.2f}")
    
    def get_current_stats(self) -> Dict:
        """Get current usage statistics"""
        today = self._get_date_key()
        this_month = self._get_month_key()
        
        return {
            'daily_cost': self.stats['daily'].get(today, 0.0),
            'daily_limit': self.DAILY_LIMIT,
            'monthly_cost': sum(self.stats['monthly'].values()),
            'monthly_limit': self.MONTHLY_LIMIT,
            'total_cost': self.stats['total_cost'],
            'total_embeddings': self.stats['total_embeddings'],
            'total_chat_requests': self.stats['total_chat_requests'],
        }
    
    def reset_daily_stats(self):
        """Reset daily statistics (call this daily via cron or scheduler)"""
        # Keep only last 30 days
        cutoff_date = datetime.now() - timedelta(days=30)
        cutoff_key = cutoff_date.strftime("%Y-%m-%d")
        
        self.stats['daily'] = {
            k: v for k, v in self.stats['daily'].items() 
            if k >= cutoff_key
        }
        self._save_stats()
