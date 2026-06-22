@echo off
REM DeepSeek 定价更新脚本
REM 用法：双击运行，或配合定时任务自动执行

echo ===== DeepSeek 定价更新 =====
echo.

REM ---- 配置区 ----
set API_URL=http://localhost:3000
set USERNAME=root
set PASSWORD=admin123456

REM Flash 定价（单位：人民币元/1M tokens）
set FLASH_INPUT=1.00
set FLASH_OUTPUT=2.00
set FLASH_CACHE=0.02

REM Pro 定价
set PRO_INPUT=3.00
set PRO_OUTPUT=6.00
set PRO_CACHE=0.025

REM ---- 以下不用改 ----
set QUOTA_PER_UNIT=500000
set USD_RATE=7.3

REM 计算 ModelRatio
set /a FLASH_MR=%FLASH_INPUT% * %QUOTA_PER_UNIT% / (%USD_RATE% * 1000000)
echo 此脚本需要配合 curl 和 Python 使用，详见说明文档。
echo.
echo 当前配置值：
echo   DeepSeek-V4-Flash: 输入=%FLASH_INPUT%元 输出=%FLASH_OUTPUT%元 缓存=%FLASH_CACHE%元
echo   DeepSeek-V4-Pro:   输入=%PRO_INPUT%元 输出=%PRO_OUTPUT%元 缓存=%PRO_CACHE%元
echo.
echo 如需更新，请修改脚本顶部的定价值后重新运行。
pause
