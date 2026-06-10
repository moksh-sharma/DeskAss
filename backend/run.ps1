# Start the Cache AI Assistant backend using the project virtual environment.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = ".\.venv\Scripts\python.exe"
$pip    = ".\.venv\Scripts\pip.exe"

if (-not (Test-Path $python)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
    & $pip install -r requirements.txt
}

# Ensure Windows event-log dependencies are present.
& $python -c "import win32con" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing pywin32 (required for Windows Event Logs)..." -ForegroundColor Yellow
    & $pip install "pywin32==308"
    & $python -m pywin32_postinstall -install 2>$null
}

$port = 8003

# Kill every listener on 8000/8003 (orphan uvicorn workers survive reloader kills).
$stalePids = @()
foreach ($p in @(8000, 8003)) {
    Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { $stalePids += $_.OwningProcess }
    netstat -ano | Select-String ":$p\s+.*LISTENING" | ForEach-Object {
        $procId = ($_.Line -split '\s+')[-1]
        if ($procId -match '^\d+$') { $stalePids += [int]$procId }
    }
}
foreach ($procId in ($stalePids | Sort-Object -Unique)) {
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "Stopping stale backend PID $procId ($($proc.ProcessName))..." -ForegroundColor Yellow
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
}
Start-Sleep -Seconds 2

Write-Host "Starting backend on http://127.0.0.1:$port" -ForegroundColor Green
Write-Host "AI logs appear here and in .\logs\backend.log" -ForegroundColor DarkGray
& $python -m uvicorn app.main:app --reload --port $port --log-level info --access-log
