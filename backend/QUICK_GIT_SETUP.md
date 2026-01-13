# Quick Git Setup for GitHub

## Step 1: Install Git (if not installed)

Download and install from: https://git-scm.com/download/win

After installation, **restart your terminal/PowerShell**.

## Step 2: Run the Setup Script

Double-click: `CONNECT_TO_GITHUB.bat` in the backend folder

OR run these commands manually:

```bash
cd c:\

# Initialize git (if not done)
git init

# Add remote (SSH version - requires SSH keys)
git remote add origin git@github.com:nicks-codes/data-center-news-chatbot.git

# Or use HTTPS (easier, no SSH setup needed):
git remote add origin https://github.com/nicks-codes/data-center-news-chatbot.git

# Add all files
git add .

# Commit
git commit -m "Initial commit"

# Set branch to main
git branch -M main

# Push to GitHub
git push -u origin main
```

## SSH vs HTTPS

**SSH** (`git@github.com:...`):
- Requires SSH keys setup
- More secure
- No password prompts after setup

**HTTPS** (`https://github.com/...`):
- Easier to set up
- May need Personal Access Token
- Works immediately

## If Push Fails

### Option 1: Use HTTPS Instead
```bash
git remote set-url origin https://github.com/nicks-codes/data-center-news-chatbot.git
git push -u origin main
```

### Option 2: Set Up SSH Keys
1. Follow: https://docs.github.com/en/authentication/connecting-to-github-with-ssh
2. Then use the SSH URL

### Option 3: Use Personal Access Token
1. GitHub → Settings → Developer settings → Personal access tokens
2. Generate new token (classic)
3. Use token as password when pushing

## After Setup - Daily Workflow

**Make changes:**
```bash
cd c:\
git add .
git commit -m "Description of changes"
git push
```

**Get updates:**
```bash
cd c:\
git pull
```
