@echo off
TITLE Launching Remote Camera + AI Platform
echo ========================================================
echo   DYNAMIC REMOTE CAMERA + AI PLATFORM - LAUNCHER
echo ========================================================
echo.

cd /d "%~dp0"

echo [1/3] Starting MediaMTX Streaming Server...
start "MediaMTX Server" cmd /k "python run_mediamtx.py"

timeout /t 2 /nobreak >nul

echo [2/3] Starting FastAPI Backend...
start "FastAPI Backend" cmd /k "python run_backend.py"

timeout /t 3 /nobreak >nul

echo [3/3] Starting React Frontend...
start "React Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo ========================================================
echo   Platform services are now launching in separate windows!
echo   - Frontend: http://localhost:5173
echo   - Backend API: http://127.0.0.1:8000/docs
echo   - Health Check: http://127.0.0.1:8000/health
echo   - MediaMTX WebRTC: http://127.0.0.1:8889
echo.
echo   Default Admin Credentials:
echo   - Email:    admin@platform.local
echo   - Password: adminpassword123
echo ========================================================
echo.
pause
