@echo off
echo Stopping all trading bot processes...
taskkill /IM python.exe /F 2>nul
if %errorlevel%==0 (
    echo All Python processes killed.
) else (
    echo No Python processes found running.
)
echo.
pause
