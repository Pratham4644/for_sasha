# PowerShell Launcher for Remote Camera + AI Platform
$ErrorActionPreference = "Stop"
$BaseDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $BaseDir

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "   DYNAMIC REMOTE CAMERA + AI PLATFORM - LAUNCHER" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

# 1. MediaMTX
Write-Host "`n[1/3] Starting MediaMTX Streaming Server..." -ForegroundColor Yellow
Start-Process cmd.exe -ArgumentList "/k", "python run_mediamtx.py"

Start-Sleep -Seconds 2

# 2. FastAPI Backend
Write-Host "[2/3] Starting FastAPI Backend..." -ForegroundColor Yellow
Start-Process cmd.exe -ArgumentList "/k", "python run_backend.py"

Start-Sleep -Seconds 3

# 3. React Frontend
Write-Host "[3/3] Starting React Vite Frontend..." -ForegroundColor Yellow
Start-Process cmd.exe -ArgumentList "/k", "cd frontend && npm run dev"

Write-Host "`n========================================================" -ForegroundColor Green
Write-Host "   All platform services launched in separate windows!" -ForegroundColor Green
Write-Host "   - Frontend UI:   http://localhost:5173" -ForegroundColor White
Write-Host "   - Backend API:   http://127.0.0.1:8000/docs" -ForegroundColor White
Write-Host "   - Health Check:  http://127.0.0.1:8000/health" -ForegroundColor White
Write-Host "   - MediaMTX:      http://127.0.0.1:8889" -ForegroundColor White
Write-Host "`n   Default Credentials:" -ForegroundColor Cyan
Write-Host "   - Email:         admin@platform.local" -ForegroundColor White
Write-Host "   - Password:      adminpassword123" -ForegroundColor White
Write-Host "========================================================`n" -ForegroundColor Green
