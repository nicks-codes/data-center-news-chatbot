@echo off
echo ========================================
echo Connecting to GitHub Repository
echo ========================================
echo.

REM Check if git is installed
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Git is not installed or not in PATH!
    echo.
    echo Please install Git from: https://git-scm.com/download/win
    echo After installing, restart this script.
    echo.
    pause
    exit /b 1
)

echo Git is installed!
git --version
echo.

REM Navigate to project root
cd /d %~dp0\..
if not exist "backend" (
    echo ERROR: Cannot find backend folder
    echo Make sure you're running this from the backend folder
    pause
    exit /b 1
)

echo Current directory: %CD%
echo.

REM Initialize git if not already done
if not exist ".git" (
    echo Initializing Git repository...
    git init
    echo.
)

REM Check if remote already exists
git remote get-url origin >nul 2>&1
if %errorlevel% equ 0 (
    echo Remote 'origin' already exists.
    echo Current remote URL:
    git remote get-url origin
    echo.
    set /p overwrite="Do you want to change it? (y/n): "
    if /i "%overwrite%"=="y" (
        git remote set-url origin git@github.com:nicks-codes/data-center-news-chatbot.git
        echo Remote updated!
    ) else (
        echo Keeping existing remote.
    )
) else (
    echo Adding GitHub remote...
    git remote add origin git@github.com:nicks-codes/data-center-news-chatbot.git
    echo Remote added!
)

echo.
echo Adding all files...
git add .
echo.

echo Creating/updating commit...
git commit -m "Sync local changes to GitHub" 2>nul
if %errorlevel% neq 0 (
    echo No changes to commit, or commit already exists.
)

echo.
echo Setting branch to main...
git branch -M main
echo.

echo ========================================
echo Ready to push!
echo.
echo NOTE: If you haven't set up SSH keys, you may need to:
echo 1. Use HTTPS instead: git remote set-url origin https://github.com/nicks-codes/data-center-news-chatbot.git
echo 2. Or set up SSH keys: https://docs.github.com/en/authentication/connecting-to-github-with-ssh
echo.
echo Attempting to push...
echo ========================================
echo.

git push -u origin main

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo SUCCESS! Your code is now on GitHub!
    echo ========================================
) else (
    echo.
    echo ========================================
    echo Push failed. Common issues:
    echo.
    echo 1. SSH keys not set up - Use HTTPS instead:
    echo    git remote set-url origin https://github.com/nicks-codes/data-center-news-chatbot.git
    echo    git push -u origin main
    echo.
    echo 2. Authentication needed - GitHub may prompt for credentials
    echo    Use a Personal Access Token as password
    echo.
    echo 3. Repository doesn't exist - Make sure it's created on GitHub first
    echo ========================================
)

echo.
pause
