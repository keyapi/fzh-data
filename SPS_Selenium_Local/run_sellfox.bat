@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Install deps (sellfox)...
pip install -r requirements.txt -q

echo.
echo Set credentials before running, e.g.:
echo   set SELLFOX_USER=your_user
echo   set SELLFOX_PASSWORD=your_password
echo.

python sellfox_login.py
echo Exit code: %ERRORLEVEL%
pause
