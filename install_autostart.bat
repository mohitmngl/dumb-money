@echo off
echo Installing bots to Windows Startup...
echo.

:: Create startup shortcut via PowerShell
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\StockBots.lnk'); $s.TargetPath = 'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\Start Both Bots.bat'; $s.WorkingDirectory = 'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt'; $s.Description = 'Auto-start stock trading bots'; $s.Save()"

if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\StockBots.lnk" (
    echo SUCCESS! Bots will auto-start on Windows login.
    echo.
    echo Location: %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\StockBots.lnk
    echo.
    echo To remove autostart, delete:
    echo   %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\StockBots.lnk
) else (
    echo FAILED to create shortcut. Try running this as Administrator.
)

echo.
pause
