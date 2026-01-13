@echo off
REM Simple backup script for Windows
echo Creating backup...

set timestamp=%date:~-4,4%-%date:~-10,2%-%date:~-7,2%_%time:~0,2%-%time:~3,2%-%time:~6,2%
set timestamp=%timestamp: =0%
set backupDir=backups
set backupName=backup_%timestamp%

if not exist "%backupDir%" mkdir "%backupDir%"
if not exist "%backupDir%\%backupName%" mkdir "%backupDir%\%backupName%"

echo Backing up to: %backupDir%\%backupName%

xcopy /E /I /Y *.py "%backupDir%\%backupName%\" >nul
xcopy /E /I /Y services "%backupDir%\%backupName%\services\" >nul
xcopy /E /I /Y scrapers "%backupDir%\%backupName%\scrapers\" >nul
xcopy /E /I /Y database "%backupDir%\%backupName%\database\" >nul
copy /Y requirements.txt "%backupDir%\%backupName%\" >nul
copy /Y scheduler.py "%backupDir%\%backupName%\" >nul
copy /Y main.py "%backupDir%\%backupName%\" >nul

echo.
echo Backup completed! Location: %backupDir%\%backupName%
echo.
pause
