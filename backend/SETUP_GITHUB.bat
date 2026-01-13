@echo off
echo ========================================
echo GitHub Setup Script
echo ========================================
echo.

REM Check if git is installed
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Git is not installed!
    echo.
    echo Please install Git from: https://git-scm.com/download/win
    echo Then run this script again.
    pause
    exit /b 1
)

echo Git is installed!
echo.

REM Navigate to project root
cd /d %~dp0\..
if not exist "backend" (
    echo ERROR: Cannot find backend folder
    echo Make sure you're running this from the correct location
    pause
    exit /b 1
)

echo Current directory: %CD%
echo.

REM Check if git is already initialized
if exist ".git" (
    echo Git repository already initialized.
    echo.
    echo To add to GitHub:
    echo 1. Create a repository on GitHub.com
    echo 2. Run these commands:
    echo    git remote add origin https://github.com/nicks-codes/data-center-news-chatbot.git
    echo    git branch -M main
    echo    git push -u origin main
    echo.
    pause
    exit /b 0
)

echo Initializing Git repository...
git init
echo.

echo Adding files to Git...
git add .
echo.

echo Creating initial commit...
git commit -m "Initial commit: Data Center News Chatbot"
echo.

echo ========================================
echo Git repository initialized!
echo.
echo Next steps:
echo 1. Create a repository on GitHub.com
    echo 2. Run these commands:
echo.
echo    git remote add origin https://github.com/nicks-codes/data-center-news-chatbot.git
echo    git branch -M main
echo    git push -u origin main
echo.
echo See GITHUB_SETUP.md for detailed instructions.
echo ========================================
pause
