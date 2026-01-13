# Backup Guide - Don't Lose Your Code! 💾

This guide will help you protect your agent and code from being lost.

## Quick Backup Methods

### Method 1: Use the Backup Script (Recommended)

Run the PowerShell backup script:
```powershell
.\backup.ps1
```

This will create a timestamped backup in the `backups/` folder with all your code.

### Method 2: Manual Copy

1. Copy the entire `c:\backend` folder to a safe location
2. Name it with a date, e.g., `backend_backup_2024-01-15`
3. Store it in a different location (external drive, cloud, etc.)

### Method 3: Use Git (Best for Version Control)

If you have Git installed:

1. **Initialize repository:**
   ```powershell
   git init
   ```

2. **Add all files (except .env):**
   ```powershell
   git add .
   git commit -m "Initial commit - Agent code"
   ```

3. **Create a remote repository on GitHub/GitLab:**
   - Go to GitHub.com and create a new repository
   - Then connect it:
   ```powershell
   git remote add origin https://github.com/nicks-codes/data-center-news-chatbot.git
   git push -u origin main
   ```

4. **Regular commits:**
   ```powershell
   git add .
   git commit -m "Description of changes"
   git push
   ```

## What to Backup

✅ **DO Backup:**
- All `.py` files
- `requirements.txt`
- `scheduler.py`
- `services/` folder
- `scrapers/` folder
- `database/` folder
- `README.md` and documentation

❌ **DON'T Backup (or keep private):**
- `.env` file (contains API keys)
- `chroma_db/` (can be regenerated)
- `__pycache__/` folders
- Virtual environments

## Automated Backup Schedule

### Windows Task Scheduler

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger (e.g., daily at 2 AM)
4. Action: Start a program
5. Program: `powershell.exe`
6. Arguments: `-File "C:\backend\backup.ps1"`

### Cloud Backup Options

- **GitHub/GitLab**: Free private repositories
- **OneDrive/Dropbox**: Automatic sync
- **Google Drive**: Manual or automatic sync
- **External Drive**: Regular manual copies

## Recovery

If you lose your code:

1. **From Backup Script:**
   - Go to `backups/` folder
   - Find the latest backup
   - Copy files back to `c:\backend`

2. **From Git:**
   ```powershell
   git clone https://github.com/nicks-codes/data-center-news-chatbot.git
   ```

3. **From Cloud/External Drive:**
   - Download/copy the backup folder
   - Restore to `c:\backend`

## Best Practices

1. ✅ **Commit frequently** - After every significant change
2. ✅ **Push to remote** - At least once a day
3. ✅ **Multiple backups** - Use both Git and local backups
4. ✅ **Test restores** - Periodically verify you can restore from backup
5. ✅ **Document changes** - Keep notes on what your agent does

## Emergency Recovery Checklist

If you've lost code:

- [ ] Check `backups/` folder
- [ ] Check Git repository (if used)
- [ ] Check cloud storage (OneDrive, Dropbox, etc.)
- [ ] Check external drives
- [ ] Check email attachments (if you sent code to yourself)
- [ ] Check browser history for GitHub/GitLab links
- [ ] Check recent file history in Windows

## Questions?

If you need help setting up backups or recovering lost code, ask for assistance!
