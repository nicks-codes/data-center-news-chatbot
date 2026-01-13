# Quick Setup Guide

## Current Status
Your app is mostly set up! However, Python 3.14 is very new and some packages (like chromadb and sentence-transformers) don't have pre-built wheels yet.

## Two Options:

### Option 1: Use Python 3.11 or 3.12 (Recommended)
1. Install Python 3.11 or 3.12 from python.org
2. Create a virtual environment:
   ```
   python3.11 -m venv venv
   venv\Scripts\activate
   ```
3. Install packages:
   ```
   pip install -r requirements.txt
   ```

### Option 2: Install Missing Packages Manually
Try installing chromadb and sentence-transformers separately:
```
pip install chromadb --no-deps
pip install sentence-transformers --no-deps
```

## To Run the App:

### Method 1: Double-click start.bat
Just double-click `start.bat` in the backend folder

### Method 2: Command Line
```bash
cd c:\
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### Method 3: Use run.py
```bash
cd c:\backend
python run.py
```

## Access the App:
Once running, open your browser to:
**http://localhost:8000**

## Current Configuration:
- ✅ Database: SQLite (no setup needed!)
- ✅ AI Provider: Groq (free - already configured)
- ⚠️ Embeddings: sentence-transformers (may need Python 3.11/3.12)
- ⚠️ Vector Store: ChromaDB (may need Python 3.11/3.12)

## If You Get Errors:
1. **Chromadb not found**: The app will still work, but vector search won't function. You can use OpenAI embeddings as fallback.
2. **Sentence-transformers not found**: The app will use OpenAI embeddings (if you have an API key) or you can install it later.

## Need Help?
The app is designed to work even if some optional packages aren't installed. The core functionality (scraping, database, chat) should work!
