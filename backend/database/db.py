from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import os
from pathlib import Path
from dotenv import load_dotenv
import hashlib
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# Load .env from multiple possible locations
env_paths = [
    Path.cwd() / ".env",
    Path(__file__).parent.parent / ".env",
    Path(__file__).parent.parent.parent / ".env",
]
for env_path in env_paths:
    if env_path.exists():
        load_dotenv(env_path)
        break
else:
    load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./datacenter_news.db")

# Fix SQLite path to be absolute and ensure directory exists
if DATABASE_URL.startswith("sqlite"):
    # Convert relative path to absolute
    if DATABASE_URL.startswith("sqlite:///./"):
        # Get the backend directory
        backend_dir = Path(__file__).parent.parent
        db_file = backend_dir / "datacenter_news.db"
        DATABASE_URL = f"sqlite:///{db_file.absolute()}"
    elif DATABASE_URL.startswith("sqlite:///"):
        # Already absolute or relative, ensure it's absolute
        db_path = DATABASE_URL.replace("sqlite:///", "")
        if not os.path.isabs(db_path):
            backend_dir = Path(__file__).parent.parent
            db_path = backend_dir / db_path
            DATABASE_URL = f"sqlite:///{db_path.absolute()}"
    
    # Ensure directory exists
    db_file_path = DATABASE_URL.replace("sqlite:///", "")
    db_dir = os.path.dirname(db_file_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, pool_pre_ping=True)
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    """Dependency for getting database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize database tables"""
    # Import models to register them with Base
    from . import models
    Base.metadata.create_all(bind=engine)

    # Lightweight SQLite migrations (no Alembic in this project).
    # These are safe no-ops if columns already exist.
    if DATABASE_URL.startswith("sqlite"):
        with engine.begin() as conn:
            # Determine existing columns
            cols = conn.execute(text("PRAGMA table_info(articles);")).fetchall()
            existing = {row[1] for row in cols}  # row[1] = name

            def _add_col_if_missing(col_name: str, ddl: str):
                if col_name in existing:
                    return
                conn.execute(text(ddl))

            _add_col_if_missing("canonical_url", "ALTER TABLE articles ADD COLUMN canonical_url VARCHAR(1000);")
            _add_col_if_missing("url_hash", "ALTER TABLE articles ADD COLUMN url_hash VARCHAR(64);")
            _add_col_if_missing("relevance_score", "ALTER TABLE articles ADD COLUMN relevance_score FLOAT;")

            # Best-effort index creation (SQLite supports IF NOT EXISTS).
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_articles_url_hash ON articles(url_hash);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_articles_canonical_url ON articles(canonical_url);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_articles_relevance_score ON articles(relevance_score);"))

            # Backfill url_hash/canonical_url for existing rows if missing.
            # This improves dedupe without requiring destructive schema changes.
            rows = conn.execute(text("SELECT id, url, canonical_url, url_hash FROM articles;")).fetchall()
            for row in rows:
                article_id, url, canonical_url, url_hash = row
                if not url:
                    continue
                if canonical_url and url_hash:
                    continue
                canon = canonical_url or canonicalize_url(url)
                h = url_hash or hash_url(canon)
                conn.execute(
                    text("UPDATE articles SET canonical_url = :c, url_hash = :h WHERE id = :id;"),
                    {"c": canon, "h": h, "id": article_id},
                )


def canonicalize_url(url: str) -> str:
    """
    Canonicalize URLs for deduplication.
    Removes fragments and common tracking params while preserving meaningful query args.
    """
    try:
        parts = urlsplit(url.strip())
        scheme = parts.scheme.lower() or "https"
        netloc = parts.netloc.lower()
        path = parts.path or "/"

        # Remove fragment
        fragment = ""

        # Drop tracking params
        drop_params = {
            "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
            "utm_id", "utm_name", "utm_reader", "utm_viz_id", "utm_pubreferrer",
            "fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "mkt_tok",
            "ref", "ref_src",
        }
        query_pairs = parse_qsl(parts.query, keep_blank_values=True)
        kept = [(k, v) for (k, v) in query_pairs if k.lower() not in drop_params]
        kept.sort(key=lambda kv: (kv[0].lower(), kv[1]))
        query = urlencode(kept, doseq=True)

        return urlunsplit((scheme, netloc, path, query, fragment))
    except Exception:
        return url.strip()


def hash_url(canonical_url: str) -> str:
    """Stable hash for canonical URLs (for fast dedupe lookups)."""
    return hashlib.sha256(canonical_url.encode("utf-8", errors="ignore")).hexdigest()
