"""
Service for generating embeddings using OpenAI API
"""
import openai
import os
from typing import List, Optional
import logging
from pathlib import Path
from dotenv import load_dotenv
from .cost_tracker import CostTracker

# Load .env from multiple possible locations
env_paths = [
    Path(__file__).parent.parent / ".env",  # Backend folder (preferred)
    Path.cwd() / ".env",  # Current directory
    Path(__file__).parent.parent.parent / ".env",  # Project root
]

for env_path in env_paths:
    if env_path.exists():
        load_dotenv(env_path, override=True)
        break
else:
    load_dotenv()

logger = logging.getLogger(__name__)

class EmbeddingService:
    """Service for generating text embeddings"""
    
    def __init__(self):
        # Try free embedding providers first, then OpenAI
        self.provider = os.getenv("EMBEDDING_PROVIDER", "sentence-transformers").lower()
        self.enabled = False
        self.client = None
        self.cost_tracker = None
        self.local_model = None
        
        # Skip embeddings entirely if provider is "none" (lightweight mode)
        if self.provider == "none":
            logger.info("Embeddings disabled (lightweight mode) - using keyword search only")
            return
        
        if self.provider == "sentence-transformers":
            # Free local embeddings using Sentence Transformers
            try:
                from sentence_transformers import SentenceTransformer
                logger.info("Loading Sentence Transformers model (free, local)...")
                # Use a lightweight, fast model
                self.local_model = SentenceTransformer('all-MiniLM-L6-v2')
                self.enabled = True
                self.cost_tracker = None  # No cost tracking for free local model
                logger.info("Sentence Transformers loaded successfully (free embeddings)")
            except ImportError:
                logger.warning("sentence-transformers not installed. Using keyword search instead.")
            except Exception as e:
                logger.warning(f"Could not load Sentence Transformers: {e}. Using keyword search instead.")
        
        # Fallback to OpenAI if local model not available
        if not self.enabled and self.provider != "none":
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                self.client = openai.OpenAI(api_key=api_key)
                self.enabled = True
                self.cost_tracker = CostTracker()
                logger.info("Using OpenAI embeddings (paid)")
            else:
                logger.info("No embedding provider available. Using keyword search only.")
    
    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for a single text"""
        if not self.enabled:
            return None
        
        try:
            # Use local Sentence Transformers model (free)
            if self.local_model:
                # Truncate text if too long
                max_length = 512  # Sentence Transformers limit
                if len(text) > max_length:
                    text = text[:max_length]
                embedding = self.local_model.encode(text, convert_to_numpy=True).tolist()
                return embedding
            
            # Use OpenAI API (paid)
            if self.client:
                # Check cost limits before making API call
                if self.cost_tracker:
                    try:
                        self.cost_tracker.record_embedding(text)
                    except Exception as e:
                        logger.error(f"Cost limit exceeded: {e}")
                        return None
                
                # Truncate text if too long
                max_length = 8000
                if len(text) > max_length:
                    text = text[:max_length]
                
                response = self.client.embeddings.create(
                    model="text-embedding-3-small",
                    input=text
                )
                
                return response.data[0].embedding
            
            return None
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None
    
    def generate_embeddings_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Generate embeddings for multiple texts"""
        if not self.enabled:
            return [None] * len(texts)
        
        embeddings = []
        
        # Use local Sentence Transformers model (free)
        if self.local_model:
            try:
                # Truncate texts if too long
                max_length = 512
                truncated_texts = [text[:max_length] if len(text) > max_length else text for text in texts]
                batch_embeddings = self.local_model.encode(truncated_texts, convert_to_numpy=True).tolist()
                return batch_embeddings
            except Exception as e:
                logger.error(f"Error generating batch embeddings with Sentence Transformers: {e}")
                return [None] * len(texts)
        
        # Use OpenAI API (paid)
        if self.client:
            # Process in batches to avoid rate limits
            batch_size = 100
            
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                try:
                    # Truncate texts
                    truncated_batch = [text[:8000] if len(text) > 8000 else text for text in batch]
                    
                    response = self.client.embeddings.create(
                        model="text-embedding-3-small",
                        input=truncated_batch
                    )
                    
                    batch_embeddings = [item.embedding for item in response.data]
                    embeddings.extend(batch_embeddings)
                except Exception as e:
                    logger.error(f"Error generating batch embeddings: {e}")
                    embeddings.extend([None] * len(batch))
        
        return embeddings
