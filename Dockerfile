# Lightweight Dockerfile for Data Center News Chatbot
# Optimized for Railway/Render free tier (< 4GB image size)
# v2 - Fixed PORT handling

FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install minimal system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create app directory
WORKDIR /app

# Copy and install production requirements (includes chromadb + embeddings)
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Create necessary directories (prefer /data for persistence)
RUN mkdir -p /data /data/chroma /data/chroma_db

# Set environment defaults (semantic retrieval via chroma + local embeddings)
ENV DATABASE_URL=sqlite:////data/datacenter_news.db \
    CHROMA_PERSIST_DIR=/data/chroma \
    CHROMA_DB_PATH=/data/chroma \
    EMBEDDING_PROVIDER=sentence-transformers \
    AI_PROVIDER=groq

# Copy and setup start script
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Expose port
EXPOSE 8000

# Run FastAPI via start script (handles PORT env var)
CMD ["/start.sh"]
