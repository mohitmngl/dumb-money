@echo off
cd /d "C:\Users\Admin\Desktop\dumb money opencode\dumbmoney"
set FLASK_PORT=2957
set DUMBMONEY_STARTUP_RECOMPUTE=0
set DUMBMONEY_STARTUP_BACKFILL=0
echo Starting DumbMoney server...
start "DumbMoney" python app.py
echo Waiting for server...
timeout /t 10 /nobreak >nul
echo Opening browser...
start http://localhost:2957/
echo Server running at http://localhost:2957/
echo Close this window to stop the server, or press Ctrl+C in the server window.
pause
