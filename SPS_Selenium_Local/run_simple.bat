@echo off
chcp 65001
cd /d "%~dp0"

echo Installing packages...
pip install webdriver-manager tzdata

echo Creating directories...
if not exist screenshots mkdir screenshots
if not exist logs mkdir logs

echo Running automation...
python sps_automation.py

echo Done!
pause
