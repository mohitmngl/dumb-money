@echo off
start "HFT Bot - 1min SuperTrend" cmd /k cd /d "C:\Users\Admin\Desktop\stock test\open code v5 claude prompt" && python -u trading_bot\run.py
start "Prob Trader - 15min" cmd /k cd /d "C:\Users\Admin\Desktop\stock test\open code v5 claude prompt" && python -u prob_trader_loop.py
