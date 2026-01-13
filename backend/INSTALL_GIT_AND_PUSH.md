# Install Git and Push to GitHub

## Step 1: Install Git

1. **Download Git**: https://git-scm.com/download/win
2. **Run the installer**
3. **Important**: During installation, make sure to check:
   - ✅ "Git from the command line and also from 3rd-party software"
   - ✅ "Use Git and optional Unix tools from the Command Prompt"
4. **Complete the installation**
5. **Restart Cursor/your terminal** (close and reopen)

## Step 2: Verify Git is Installed

Open a **NEW** PowerShell/Terminal window and run:
```bash
git --version
```

You should see something like: `git version 2.x.x`

## Step 3: Run These Commands

Once Git is installed, open PowerShell in `c:\` and run:

```bash
cd c:\

# Add remote (using HTTPS from GitHub)
git remote add origin https://github.com/nicks-codes/data-center-news-chatbot.git

# Add all files
git add .

# Commit
git commit -m "Initial commit: Data Center News Chatbot"

# Set branch to main
git branch -M main

# Push to GitHub
git push -u origin main
```

## Step 4: Authentication

When you run `git push`, GitHub will ask for credentials:

1. **Username**: Your GitHub username (`nicks-codes`)
2. **Password**: Use a **Personal Access Token** (not your GitHub password)

### How to Create a Personal Access Token:

1. Go to: https://github.com/settings/tokens
2. Click **Generate new token** → **Generate new token (classic)**
3. Name it: "Data Center Chatbot"
4. Select scopes: Check **repo** (this gives full repository access)
5. Click **Generate token**
6. **Copy the token immediately** (you won't see it again!)
7. Use this token as your password when pushing

## Alternative: Use GitHub Desktop

If you prefer a GUI instead of command line:

1. Download: https://desktop.github.com/
2. Install and sign in
3. File → Add Local Repository → Select `c:\`
4. Click "Publish repository" button
5. Done! You can push/pull with buttons

## Troubleshooting

### "Git is not recognized"
- Make sure you **restarted your terminal** after installing Git
- Try closing and reopening Cursor completely

### "Remote already exists"
```bash
git remote remove origin
git remote add origin https://github.com/nicks-codes/data-center-news-chatbot.git
```

### "Authentication failed"
- Make sure you're using a Personal Access Token, not your password
- Token needs `repo` scope

### "Repository not found"
- Make sure the repository exists on GitHub
- Check the URL is correct: https://github.com/nicks-codes/data-center-news-chatbot
