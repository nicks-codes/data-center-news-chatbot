"""
Vector store service using ChromaDB for semantic search
"""
import os
from typing import List, Dict, Optional, Tuple
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Try to import chromadb, but handle if it's not installed
try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logger.warning("ChromaDB not installed. Vector search will be disabled. Install with: pip install chromadb")

class VectorStore:
    """Service for managing vector embeddings in ChromaDB"""
    
    def __init__(self):
        if not CHROMADB_AVAILABLE:
            self.client = None
            self.collection = None
            logger.warning("VectorStore initialized but ChromaDB is not available")
            return
            
        # Initialize ChromaDB
        persist_directory = os.getenv("CHROMA_DB_PATH", "./chroma_db")
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self.client.get_or_create_collection(
            name="datacenter_articles",
            metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"ChromaDB initialized at {persist_directory}")
    
    def add_article(self, article_id: str, embedding: List[float], metadata: Dict) -> bool:
        """Add an article embedding to the vector store"""
        if not CHROMADB_AVAILABLE or not self.collection:
            logger.warning("ChromaDB not available, cannot add article")
            return False
        try:
            self.collection.add(
                ids=[article_id],
                embeddings=[embedding],
                metadatas=[metadata]
            )
            return True
        except Exception as e:
            logger.error(f"Error adding article to vector store: {e}")
            return False
    
    def add_articles_batch(self, article_ids: List[str], embeddings: List[List[float]], metadatas: List[Dict]) -> bool:
        """Add multiple articles to the vector store"""
        if not CHROMADB_AVAILABLE or not self.collection:
            logger.warning("ChromaDB not available, cannot add articles")
            return False
        try:
            self.collection.add(
                ids=article_ids,
                embeddings=embeddings,
                metadatas=metadatas
            )
            return True
        except Exception as e:
            logger.error(f"Error adding articles batch to vector store: {e}")
            return False
    
    def search_similar(self, query_embedding: List[float], n_results: int = 5) -> List[Dict]:
        """Search for similar articles using semantic search"""
        if not CHROMADB_AVAILABLE or not self.collection:
            logger.warning("ChromaDB not available, cannot search")
            return []
        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results
            )
            
            # Format results
            articles = []
            if results['ids'] and len(results['ids'][0]) > 0:
                for i in range(len(results['ids'][0])):
                    article = {
                        'id': results['ids'][0][i],
                        'metadata': results['metadatas'][0][i],
                        'distance': results['distances'][0][i] if 'distances' in results else None
                    }
                    articles.append(article)
            
            return articles
        except Exception as e:
            logger.error(f"Error searching vector store: {e}")
            return []
    
    def delete_article(self, article_id: str) -> bool:
        """Delete an article from the vector store"""
        if not CHROMADB_AVAILABLE or not self.collection:
            return False
        try:
            self.collection.delete(ids=[article_id])
            return True
        except Exception as e:
            logger.error(f"Error deleting article from vector store: {e}")
            return False
    
    def get_collection_size(self) -> int:
        """Get the number of articles in the collection"""
        if not CHROMADB_AVAILABLE or not self.collection:
            return 0
        try:
            return self.collection.count()
        except Exception as e:
            logger.error(f"Error getting collection size: {e}")
            return 0
