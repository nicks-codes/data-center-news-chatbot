# 🚀 Quick Start Guide

## ✅ What's Already Done:
- ✅ All code is written and ready
- ✅ Configuration file (`.env`) is set up
- ✅ Database will use SQLite (no setup needed!)
- ✅ Groq API key is configured (free AI)

## 🎯 To Start the App:

### Easiest Way - Double Click:
1. Go to the `c:\backend` folder
2. Double-click `start.bat`
3. Wait for "Application startup complete"
4. Open browser to: **http://localhost:8000**

### Alternative - Command Line:
```bash
cd c:\
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

## ⚠️ Known Issue:
Python 3.14 is very new. Some packages (chromadb, sentence-transformers) may not install.

**Don't worry!** The app will still work:
- ✅ Scraping will work
- ✅ Database will work  
- ✅ Chat will work (using Groq API)
- ⚠️ Vector search might be limited (but chat still works!)

## 🔧 If You Want Full Features:

### Option 1: Use Python 3.11 or 3.12
1. Download from python.org
2. Create virtual environment:
   ```
   python3.11 -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```

### Option 2: Install Packages One by One
```bash
pip install chromadb
pip install sentence-transformers
```

## 📝 What the App Does:
1. **Scrapes** data center news from multiple sources every 30 minutes
2. **Stores** articles in a database
3. **Answers questions** about data center news using AI
4. **Tracks costs** to prevent overspending

## 🎉 You're All Set!
Just run `start.bat` and open http://localhost:8000 in your browser!
