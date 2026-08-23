@echo off
title Stock Trading Bots - Live
cd /d "C:\Users\Admin\Desktop\stock test\open code v5 claude prompt"

echo ============================================
echo   Starting Trading Bots (Live Windows)
echo ============================================
echo.

echo Starting HFT Bot in new window...
start "HFT Bot - 1min SuperTrend" cmd /k "cd /d "C:\Users\Admin\Desktop\stock test\open code v5 claude prompt" && python -u trading_bot\run.py"

echo Starting Probability Trader in new window...
start "Prob Trader - 15min" cmd /k "cd /d "C:\Users\Admin\Desktop\stock test\open code v5 claude prompt" && python -u prob_trader_loop.py"

echo.
echo Two windows opened. Close this one if you want.
