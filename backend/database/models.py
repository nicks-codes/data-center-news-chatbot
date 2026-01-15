"""
Database models for articles
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Index, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
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


class Conversation(Base):
    """
    Server-side persisted conversation state.
    Use a UUID string id so clients can store it safely.
    """
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    title = Column(String(160), nullable=True, index=True)
    audience = Column(String(50), nullable=True, index=True)
    memory_summary = Column(Text, nullable=True)

    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    """Persisted message turns for a conversation."""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String(36), ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False, index=True)  # user / assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    tokens_est = Column(Integer, nullable=True)

    conversation = relationship("Conversation", back_populates="messages")


class Feedback(Base):
    """User feedback on assistant messages."""
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String(36), ForeignKey("conversations.id"), nullable=False, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=True, index=True)
    rating = Column(String(10), nullable=False)  # up / down
    tag = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class Digest(Base):
    """Daily news digest for a given audience."""
    __tablename__ = "digests"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    audience = Column(String(30), nullable=False, index=True, default="DC_RE")
    title = Column(String(200), nullable=False)
    content_md = Column(Text, nullable=False)
    sources_json = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_digests_date", "date"),
    )


class StorySummary(Base):
    """Cached AI summary + key facts for an article."""
    __tablename__ = "story_summaries"

    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey("articles.id"), nullable=False, index=True)
    summary_md = Column(Text, nullable=False)
    key_facts_json = Column(Text, nullable=True)
    model = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_story_summaries_article", "article_id"),
    )
