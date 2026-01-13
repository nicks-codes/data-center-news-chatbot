from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from pathlib import Path
from dotenv import load_dotenv

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