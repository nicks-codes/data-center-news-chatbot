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

# Copy and install lightweight requirements (includes chromadb + openai)
COPY backend/requirements-light.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Create necessary directories
RUN mkdir -p /app/data /data/chroma_db

# Set environment defaults (semantic retrieval via chroma + OpenAI embeddings when OPENAI_API_KEY is set)
ENV DATABASE_URL=sqlite:///./data/datacenter_news.db \
    CHROMA_DB_PATH=/data/chroma_db \
    EMBEDDING_PROVIDER=openai \
    AI_PROVIDER=groq

# Copy and setup start script
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Expose port
EXPOSE 8000

# Run FastAPI via start script (handles PORT env var)
CMD ["/start.sh"]
