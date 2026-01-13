# Multi-stage Dockerfile for Data Center News Chatbot
# Supports both FastAPI backend and Streamlit frontend

FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements first for better caching
COPY backend/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir streamlit gunicorn

# Copy application code
COPY backend/ ./backend/
COPY frontend/ ./frontend/ 2>/dev/null || true

# Create necessary directories
RUN mkdir -p /app/data /app/chroma_db

# Set environment defaults
ENV DATABASE_URL=sqlite:///./data/datacenter_news.db \
    CHROMA_DB_PATH=/app/chroma_db \
    EMBEDDING_PROVIDER=sentence-transformers \
    AI_PROVIDER=groq

# Expose ports
EXPOSE 8000 8501

# Default command runs FastAPI
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]


# ============================================
# Alternative targets for different deployments
# ============================================

# Target: FastAPI only
FROM base as fastapi
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Target: Streamlit only
FROM base as streamlit
WORKDIR /app/backend
EXPOSE 8501
ENV API_URL=http://localhost:8000
CMD ["streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]

# Target: Both services (for development)
FROM base as full
EXPOSE 8000 8501
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh 2>/dev/null || true
CMD ["sh", "-c", "python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000"]
