# Deployment Guide - Data Center News Chatbot

This guide covers deploying the Data Center News Chatbot to various cloud platforms.

## 🚀 Quick Start Options

### Option 1: Railway (Easiest - One Click)
[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template)

1. Click the button above or go to [Railway.app](https://railway.app)
2. Connect your GitHub repository
3. Add environment variables in the dashboard:
   - `GROQ_API_KEY` - Get free at [console.groq.com](https://console.groq.com)
   - `CHROMA_PERSIST_DIR=/data/chroma_db`
4. Add a persistent volume mounted at `/data` (Railway Volumes)
5. Deploy!

### Option 2: Render
1. Go to [Render Dashboard](https://dashboard.render.com)
2. Create a new Web Service
3. Connect your GitHub repo
4. Use these settings:
   - **Build Command:** `pip install -r backend/requirements.txt`
   - **Start Command:** `cd backend && python -m uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add environment variables (see below)

### Option 3: Fly.io
```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Login and deploy
fly auth login
fly launch
fly secrets set GROQ_API_KEY=your_key_here
fly deploy
```

### Option 4: Docker (Self-hosted)
```bash
# Build the image
docker build -t datacenter-news-chatbot .

# Run with environment variables
docker run -d \
  -p 8000:8000 \
  -e GROQ_API_KEY=your_key_here \
  -e CHROMA_PERSIST_DIR=/data/chroma_db \
  -v datacenter_data:/data \
  datacenter-news-chatbot
```

## 📋 Required Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | Yes* | Free API key from [Groq](https://console.groq.com) |
| `AI_PROVIDER` | No | `groq` (default), `together`, or `openai` |
| `EMBEDDING_PROVIDER` | No | `sentence-transformers` (default, free) or `openai` |
| `DATABASE_URL` | No | SQLite default, or PostgreSQL URL |
| `CHROMA_PERSIST_DIR` | No | Persistent ChromaDB path (e.g. `/data/chroma_db`) |
| `LOG_LEVEL` | No | Log level: `INFO` (prod), `DEBUG` (dev) |

*Or use `TOGETHER_API_KEY` or `OPENAI_API_KEY` instead

## 🔧 Optional Environment Variables

### For Reddit Scraping
```env
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_USER_AGENT=DataCenterNewsBot/2.0
```
Get credentials at: https://www.reddit.com/prefs/apps

### For Twitter/X Scraping
```env
TWITTER_BEARER_TOKEN=your_bearer_token
```
Get credentials at: https://developer.twitter.com

### Cost Limits (for paid APIs)
```env
DAILY_COST_LIMIT=1.00
MONTHLY_COST_LIMIT=10.00
```

### Scraping Settings
```env
SCRAPE_INTERVAL_MINUTES=30
RELEVANCE_THRESHOLD=0.2
```

## 🌐 Platform-Specific Instructions

### Railway
Railway automatically detects the Dockerfile. Just:
1. Push to GitHub
2. Connect repo in Railway
3. Add secrets in the Variables tab
4. Railway handles the rest

### Render
The `render.yaml` file is included for automatic setup:
1. Connect your GitHub repo
2. Render detects the config
3. Add secrets in the Environment tab

For persistent storage, add a disk mount at `/data`.

### Fly.io
```bash
# Create the app
fly launch --name datacenter-news

# Create a volume for data persistence
fly volumes create data --size 1

# Set secrets
fly secrets set GROQ_API_KEY=your_key

# Deploy
fly deploy
```

### Heroku
```bash
# Login
heroku login

# Create app
heroku create datacenter-news-chatbot

# Set environment variables
heroku config:set GROQ_API_KEY=your_key
heroku config:set AI_PROVIDER=groq

# Deploy
git push heroku main
```

Add a `Procfile`:
```
web: cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT
```

### DigitalOcean App Platform
1. Go to [DigitalOcean Apps](https://cloud.digitalocean.com/apps)
2. Create new app from GitHub
3. Configure:
   - **Type:** Web Service
   - **Build Command:** `pip install -r backend/requirements.txt`
   - **Run Command:** `cd backend && uvicorn main:app --host 0.0.0.0 --port 8080`
4. Add environment variables

### Google Cloud Run
```bash
# Build and push
gcloud builds submit --tag gcr.io/PROJECT_ID/datacenter-news

# Deploy
gcloud run deploy datacenter-news \
  --image gcr.io/PROJECT_ID/datacenter-news \
  --platform managed \
  --set-env-vars GROQ_API_KEY=your_key
```

### AWS (Elastic Beanstalk)
1. Install EB CLI: `pip install awsebcli`
2. Initialize: `eb init -p docker datacenter-news`
3. Create environment: `eb create production`
4. Set env vars: `eb setenv GROQ_API_KEY=your_key`

## 🖥️ Running Streamlit UI

The Streamlit interface provides a modern chat UI. You can run it alongside or instead of the built-in frontend.

### Local Development
```bash
# Terminal 1: Run FastAPI backend
cd backend
uvicorn main:app --reload --port 8000

# Terminal 2: Run Streamlit
cd backend
streamlit run streamlit_app.py --server.port 8501
```

### Production with Both Services
Use Docker Compose:

```yaml
# docker-compose.yml
version: '3.8'
services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - GROQ_API_KEY=${GROQ_API_KEY}
    volumes:
      - data:/app/data

  ui:
    build:
      context: .
      target: streamlit
    ports:
      - "8501:8501"
    environment:
      - API_URL=http://api:8000
    depends_on:
      - api

volumes:
  data:
```

Run with:
```bash
docker-compose up -d
```

## 📊 Monitoring & Logs

### View logs
```bash
# Railway
railway logs

# Fly.io
fly logs

# Docker
docker logs container_name

# Render
# View in dashboard under Logs tab
```

### Health Check
All deployments include a health endpoint:
```
GET /health
```

## 🔄 Updating

### Railway/Render/Fly
Push to GitHub - automatic redeploy!

### Docker
```bash
docker pull your-image:latest
docker-compose up -d
```

## 🛟 Troubleshooting

### "No articles found"
- Wait for initial scrape (runs on startup, then every 30 minutes)
- Check logs for scraper errors
- Verify network connectivity

### "AI service not available"
- Check `GROQ_API_KEY` is set correctly
- Verify API key is valid at console.groq.com

### Database errors
- Ensure write permissions on data directory
- For PostgreSQL, check connection string format

### Memory issues
- Sentence-transformers needs ~500MB RAM
- Upgrade to larger instance if needed

## 💡 Tips

1. **Start with free tier** - Groq + sentence-transformers = $0 cost
2. **Enable Reddit** for community discussions (free API)
3. **Use PostgreSQL** for production (SQLite is fine for testing)
4. **Set up monitoring** - check the `/api/stats` endpoint
5. **Configure cost limits** if using OpenAI
