@echo off
title Stock Trading Bots
cd /d "C:\Users\Admin\Desktop\stock test\open code v5 claude prompt"

echo ============================================
echo   Starting Both Trading Bots...
echo ============================================
echo.

echo [1/2] Starting HFT Bot (1-min SuperTrend)...
start "HFT Bot" /min cmd /c "cd /d "C:\Users\Admin\Desktop\stock test\open code v5 claude prompt" && python -u trading_bot\run.py >> bot_output.log 2>&1"
echo       HFT Bot started in background.
echo.

echo [2/2] Starting Probability Trader (15-min)...
start "Prob Trader" /min cmd /c "cd /d "C:\Users\Admin\Desktop\stock test\open code v5 claude prompt" && python -u prob_trader_loop.py >> trader_output.log 2>&1"
echo       Probability Trader started in background.
echo.

echo ============================================
echo   Both bots are running in background.
echo   Logs: bot_output.log, trader_output.log
echo   To stop: close this window, then
echo   taskkill /IM python.exe /F
echo ============================================
echo.
echo Press any key to minimize this window (bots keep running)...
pause >nul
