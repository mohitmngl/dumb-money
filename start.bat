@echo off
echo Starting DumbMoney...
echo.
set PYTHON=C:\Users\Admin\miniforge3\envs\ipopt312\python.exe
echo Checking Python...
%PYTHON% --version
if errorlevel 1 (
    echo Python not found. Please install Python 3.8+
    pause
    exit /b 1
)
echo.
echo Starting server on http://localhost:8474
echo.
start /b cmd /c "timeout /t 2 /nobreak > nul && start http://localhost:8474"
%PYTHON% -m dumbmoney.app
pause
