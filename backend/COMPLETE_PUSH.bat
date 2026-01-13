@echo off
echo ========================================
echo Complete Push to GitHub
echo ========================================
echo.

REM Check if git is installed
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Git is not installed!
    pause
    exit /b 1
)

cd /d %~dp0

echo Fixing remote URL...
git remote remove origin 2>nul
git remote add origin https://github.com/nicks-codes/data-center-news-chatbot.git
echo Remote set to: https://github.com/nicks-codes/data-center-news-chatbot.git
echo.

echo Adding all files...
git add .
echo.

echo Committing...
git commit -m "Initial commit: Data Center News Chatbot" 2>nul
if %errorlevel% neq 0 (
    echo No changes to commit or already committed.
)
echo.

echo Setting branch to main...
git branch -M main
echo.

echo ========================================
echo Pushing to GitHub...
echo You may be prompted for credentials.
echo ========================================
echo.

git push -u origin main

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo SUCCESS! Code pushed to GitHub!
    echo ========================================
) else (
    echo.
    echo ========================================
    echo Push failed. You may need to:
    echo 1. Create Personal Access Token: https://github.com/settings/tokens
    echo 2. Use token as password when prompted
    echo ========================================
)

pause
