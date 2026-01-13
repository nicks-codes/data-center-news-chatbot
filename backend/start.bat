@echo off
echo Starting Data Center News Chatbot...
echo.
cd /d %~dp0
cd ..
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
pause
