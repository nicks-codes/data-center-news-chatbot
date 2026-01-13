@echo off
echo ========================================
echo Push to GitHub - Data Center Chatbot
echo ========================================
echo.

REM Check if git is installed
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ========================================
    echo ERROR: Git is not installed!
    echo ========================================
    echo.
    echo Please install Git first:
    echo 1. Download from: https://git-scm.com/download/win
    echo 2. Install with default options
    echo 3. Restart this script
    echo.
    echo Opening download page...
    start https://git-scm.com/download/win
    pause
    exit /b 1
)

echo Git is installed: 
git --version
echo.

REM Navigate to project root
cd /d %~dp0\..
if not exist "backend" (
    echo ERROR: Cannot find backend folder
    pause
    exit /b 1
)

echo Current directory: %CD%
echo.

REM Check if remote exists
git remote get-url origin >nul 2>&1
if %errorlevel% neq 0 (
    echo Adding GitHub remote...
    git remote add origin https://github.com/nicks-codes/data-center-news-chatbot.git
    echo Remote added!
) else (
    echo Remote already exists:
    git remote get-url origin
    echo.
    set /p update="Update remote URL? (y/n): "
    if /i "!update!"=="y" (
        git remote set-url origin https://github.com/nicks-codes/data-center-news-chatbot.git
        echo Remote updated!
    )
)

echo.
echo Adding all files...
git add .
echo.

echo Committing changes...
git commit -m "Update: Data Center News Chatbot" 2>nul
if %errorlevel% neq 0 (
    echo No changes to commit or already committed.
)

echo.
echo Setting branch to main...
git branch -M main
echo.

echo ========================================
echo Pushing to GitHub...
echo.
echo NOTE: You may be prompted for:
echo - Username: nicks-codes
echo - Password: Use a Personal Access Token (not your GitHub password)
echo.
echo Get token from: https://github.com/settings/tokens
echo ========================================
echo.

git push -u origin main

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo SUCCESS! Your code is on GitHub!
    echo ========================================
    echo.
    echo View it at: https://github.com/nicks-codes/data-center-news-chatbot
) else (
    echo.
    echo ========================================
    echo Push failed. Common solutions:
    echo.
    echo 1. Create Personal Access Token:
    echo    https://github.com/settings/tokens
    echo    - Click "Generate new token (classic)"
    echo    - Check "repo" scope
    echo    - Copy the token
    echo    - Use it as password when prompted
    echo.
    echo 2. Or use GitHub Desktop (GUI):
    echo    https://desktop.github.com/
    echo ========================================
)

echo.
pause
