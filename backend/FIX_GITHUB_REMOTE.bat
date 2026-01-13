@echo off
echo ========================================
echo Fixing GitHub Remote URL
echo ========================================
echo.

REM Check if git is installed
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Git is not installed!
    echo Please install Git first: https://git-scm.com/download/win
    pause
    exit /b 1
)

echo Git is installed!
echo.

REM Navigate to backend folder
cd /d %~dp0
if not exist ".git" (
    echo ERROR: Not a git repository. Run git init first.
    pause
    exit /b 1
)

echo Current directory: %CD%
echo.

echo Checking current remote...
git remote -v
echo.

echo Removing old remote (if exists)...
git remote remove origin 2>nul
echo.

echo Adding correct remote URL...
git remote add origin https://github.com/nicks-codes/data-center-news-chatbot.git
echo.

echo Verifying remote URL...
git remote -v
echo.

echo ========================================
echo Remote fixed! Now run:
echo.
echo   git add .
echo   git commit -m "Initial commit"
echo   git branch -M main
echo   git push -u origin main
echo ========================================
echo.
pause
