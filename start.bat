@echo off
title FinAgent Launcher
echo ================================
echo   FinAgent - Starting...
echo ================================
echo.

cd /d "%~dp0"

set PYTHON=C:\ProgramData\Anaconda3\python.exe
set NODE_DIR=C:\Users\XCH\.trae-cn\binaries\node\versions\24.15.0
set PATH=%NODE_DIR%;%PATH%

echo [1/2] Starting backend (port 8000)...
start "FinAgent-Backend" cmd /k "%PYTHON%" -m uvicorn fin_agent.bootstrap.app:create_default_app --factory --host 0.0.0.0 --port 8000

ping -n 4 127.0.0.1 >nul

echo [2/2] Starting frontend (port 5173)...
cd frontend
start "FinAgent-Frontend" cmd /k npm run dev

echo.
echo ================================
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:5173
echo ================================
echo.
echo Opening browser in 6 seconds...
ping -n 7 127.0.0.1 >nul
start http://localhost:5173
