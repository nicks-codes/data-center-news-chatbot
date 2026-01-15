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
    logger.info("ChromaDB not installed. Vector search disabled (optional). Install with: pip install chromadb")

class VectorStore:
    """Service for managing vector embeddings in ChromaDB"""
    
    def __init__(self):
        if not CHROMADB_AVAILABLE:
            self.client = None
            self.collection = None
            logger.info("VectorStore initialized without ChromaDB (keyword search only)")
            return
            
        # Initialize ChromaDB (prefer persistent disk when available)
        default_path = "/data/chroma" if os.path.isdir("/data") else "./chroma_db"
        persist_directory = (
            os.getenv("CHROMA_PERSIST_DIR")
            or os.getenv("CHROMA_DB_PATH")
            or default_path
        )
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self.client.get_or_create_collection(
            name="datacenter_articles",
            metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"ChromaDB initialized at {persist_directory}")
    
    def add_article(self, article_id: str, embedding: List[float], metadata: Dict, document: Optional[str] = None) -> bool:
        """Add an article embedding to the vector store"""
        if not CHROMADB_AVAILABLE or not self.collection:
            logger.debug("ChromaDB not available, cannot add article")
            return False
        try:
            # Use upsert when available to make indexing idempotent
            upsert = getattr(self.collection, "upsert", None)
            if callable(upsert):
                if document is not None:
                    upsert(ids=[article_id], embeddings=[embedding], metadatas=[metadata], documents=[document])
                else:
                    upsert(ids=[article_id], embeddings=[embedding], metadatas=[metadata])
            else:
                if document is not None:
                    self.collection.add(ids=[article_id], embeddings=[embedding], metadatas=[metadata], documents=[document])
                else:
                    self.collection.add(ids=[article_id], embeddings=[embedding], metadatas=[metadata])
            return True
        except Exception as e:
            logger.error(f"Error adding article to vector store: {e}")
            return False
    
    def add_articles_batch(
        self,
        article_ids: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict],
        documents: Optional[List[str]] = None,
    ) -> bool:
        """Add multiple articles to the vector store"""
        if not CHROMADB_AVAILABLE or not self.collection:
            logger.debug("ChromaDB not available, cannot add articles")
            return False
        try:
            upsert = getattr(self.collection, "upsert", None)
            if callable(upsert):
                if documents is not None:
                    upsert(ids=article_ids, embeddings=embeddings, metadatas=metadatas, documents=documents)
                else:
                    upsert(ids=article_ids, embeddings=embeddings, metadatas=metadatas)
            else:
                if documents is not None:
                    self.collection.add(ids=article_ids, embeddings=embeddings, metadatas=metadatas, documents=documents)
                else:
                    self.collection.add(ids=article_ids, embeddings=embeddings, metadatas=metadatas)
            return True
        except Exception as e:
            logger.error(f"Error adding articles batch to vector store: {e}")
            return False
    
    def search_similar(self, query_embedding: List[float], n_results: int = 5) -> List[Dict]:
        """Search for similar articles using semantic search"""
        if not CHROMADB_AVAILABLE or not self.collection:
            logger.debug("ChromaDB not available, cannot search")
            return []
        try:
            try:
                results = self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=n_results,
                    include=["metadatas", "distances", "documents"],
                )
            except TypeError:
                # Older Chroma versions don't support include
                results = self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=n_results,
                )
            
            # Format results
            articles = []
            if results['ids'] and len(results['ids'][0]) > 0:
                for i in range(len(results['ids'][0])):
                    article = {
                        'id': results['ids'][0][i],
                        'metadata': results['metadatas'][0][i],
                        'distance': results['distances'][0][i] if 'distances' in results else None,
                        'document': (results.get('documents') or [[None]])[0][i] if 'documents' in results else None,
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

    def delete_by_article_id(self, article_id: int) -> bool:
        """Delete all vectors associated with a given DB article id (chunked indexing)."""
        if not CHROMADB_AVAILABLE or not self.collection:
            return False
        try:
            # Preferred: delete via metadata filter (works even when chunk IDs vary)
            self.collection.delete(where={"article_id": int(article_id)})
            return True
        except Exception as e:
            logger.warning(f"Error deleting vectors for article_id={article_id}: {e}")
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
