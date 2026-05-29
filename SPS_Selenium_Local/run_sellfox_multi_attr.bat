@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Requires: SELLFOX_USER, SELLFOX_PASSWORD (same as sellfox login)
python sellfox_multi_attr_setup.py
echo Exit: %ERRORLEVEL%
pause
