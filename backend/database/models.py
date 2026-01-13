"""
Database models for articles
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Index
from sqlalchemy.sql import func
from .db import Base

class Article(Base):
    __tablename__ = "articles"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False, index=True)
    content = Column(Text, nullable=False)
    url = Column(String(1000), unique=True, nullable=False, index=True)
    source = Column(String(200), nullable=False, index=True)
    source_type = Column(String(50), nullable=False)  # rss, web, reddit, twitter, google_news
    published_date = Column(DateTime, nullable=True, index=True)
    scraped_date = Column(DateTime, server_default=func.now(), nullable=False)
    author = Column(String(200), nullable=True)
    tags = Column(String(500), nullable=True)
    has_embedding = Column(Boolean, default=False, nullable=False)
    embedding_id = Column(String(200), nullable=True)

    # AI-generated summary (cached)
    summary = Column(Text, nullable=True)
    summary_model = Column(String(100), nullable=True)
    summary_created_at = Column(DateTime, nullable=True)
    
    # Indexes for better query performance
    __table_args__ = (
        Index('idx_source_type', 'source_type'),
        Index('idx_published_date', 'published_date'),
    )
    
    def __repr__(self):
        return f"<Article(id={self.id}, title='{self.title[:50]}...', source='{self.source}')>"
