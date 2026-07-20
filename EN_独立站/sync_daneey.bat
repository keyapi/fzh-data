@echo off
REM ============================================================
REM 独立站产品链接同步 - 定时任务入口
REM 每天 5:40 / 13:40 / 21:40 执行
REM ============================================================
cd /d D:\Claude Demo\fzh-data\EN_独立站

REM 写入日志（保留最近30天）
set LOG_DIR=.\out\logs
if not exist %LOG_DIR% mkdir %LOG_DIR%
set LOG_FILE=%LOG_DIR%\sync_%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%.log

echo [%date% %time%] 开始同步 >> %LOG_FILE%

REM 从 API 拉取独立站数据 → 匹配 → 写入生产系统
python shopify_to_en.py --mode api --env prod >> %LOG_FILE% 2>&1

echo [%date% %time%] 同步完成 >> %LOG_FILE%
echo. >> %LOG_FILE%

REM 清理30天前的日志
forfiles /p %LOG_DIR% /m *.log /d -30 /c "cmd /c del @path" 2>nul
