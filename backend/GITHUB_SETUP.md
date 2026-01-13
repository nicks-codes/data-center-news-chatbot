# 🚀 GitHub Setup Guide

Follow these steps to add your project to GitHub and access it from your work computer.

## Step 1: Install Git (if not installed)

### On Windows:
1. Download Git from: https://git-scm.com/download/win
2. Run the installer (use default options)
3. Restart your terminal/PowerShell

### Verify installation:
```bash
git --version
```

## Step 2: Create a GitHub Account (if you don't have one)

1. Go to https://github.com
2. Sign up for a free account
3. Verify your email

## Step 3: Create a New Repository on GitHub

1. Go to https://github.com/new
2. Repository name: `data-center-news-chatbot` (or any name you like)
3. Description: "AI-powered chatbot for data center industry news"
4. Choose **Private** (recommended) or **Public**
5. **DO NOT** initialize with README, .gitignore, or license (we already have these)
6. Click **Create repository**

## Step 4: Initialize Git in Your Project

Open PowerShell/Terminal in the `c:\` directory and run:

```bash
cd c:\

# Initialize git repository
git init

# Add all files (except those in .gitignore)
git add .

# Create first commit
git commit -m "Initial commit: Data Center News Chatbot"

# Add your GitHub repository as remote
git remote add origin https://github.com/nicks-codes/data-center-news-chatbot.git

# Rename main branch to main (if needed)
git branch -M main

# Push to GitHub
git push -u origin main
```

## Step 5: Set Up on Your Work Computer

### Option A: Clone the Repository

1. Open Cursor on your work computer
2. Open terminal in Cursor
3. Navigate to where you want the project:
   ```bash
   cd C:\Projects  # or wherever you want it
   ```
4. Clone the repository:
   ```bash
   git clone https://github.com/nicks-codes/data-center-news-chatbot.git
   cd data-center-news-chatbot
   ```
5. Open the folder in Cursor:
   - File → Open Folder → Select the `data-center-news-chatbot` folder

### Option B: Open Directly in Cursor

1. In Cursor, go to: **File → Clone Repository**
2. Paste: `https://github.com/nicks-codes/data-center-news-chatbot.git`
3. Choose where to save it
4. Click **Clone**

## Step 6: Set Up Environment on Work Computer

1. Copy `.env.example` to `.env`:
   ```bash
   cd backend
   copy .env.example .env
   ```
2. Edit `.env` and add your API keys (same as on your home computer)
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Important Notes

### ⚠️ Never Commit These Files:
- `.env` (contains your API keys!)
- `*.db` (database files)
- `chroma_db/` (vector database)
- `cost_stats.json` (cost tracking data)

These are already in `.gitignore` so they won't be committed.

### 🔄 Daily Workflow:

**On Home Computer:**
```bash
cd c:\
git add .
git commit -m "Description of changes"
git push
```

**On Work Computer:**
```bash
cd C:\Projects\data-center-news-chatbot
git pull
```

### 📝 Making Changes:

1. Make your changes
2. Test them
3. Commit:
   ```bash
   git add .
   git commit -m "What you changed"
   git push
   ```
4. Pull on the other computer:
   ```bash
   git pull
   ```

## Troubleshooting

### "Git is not recognized"
- Install Git from https://git-scm.com/download/win
- Restart your terminal

### "Permission denied" when pushing
- You may need to authenticate
- GitHub now uses Personal Access Tokens instead of passwords
- Create one: GitHub → Settings → Developer settings → Personal access tokens → Generate new token
- Use the token as your password when pushing

### "Repository not found"
- Check the repository name matches
- Make sure you have access (if it's private, you need to be added as collaborator)

### Files not syncing
- Make sure you're committing and pushing:
  ```bash
  git add .
  git commit -m "Your message"
  git push
  ```
- On the other computer, make sure you pull:
  ```bash
  git pull
  ```

## Quick Reference

```bash
# Check status
git status

# See what changed
git diff

# Add all changes
git add .

# Commit changes
git commit -m "Your message here"

# Push to GitHub
git push

# Pull latest changes
git pull

# See commit history
git log
```

## Need Help?

- Git documentation: https://git-scm.com/doc
- GitHub guides: https://guides.github.com
- Git cheat sheet: https://education.github.com/git-cheat-sheet-education.pdf
