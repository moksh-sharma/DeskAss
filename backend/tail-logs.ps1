# Follow backend logs in real time (useful when the IDE file view does not auto-refresh).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$logFile = Join-Path $PSScriptRoot "logs\backend.log"
if (-not (Test-Path $logFile)) {
    Write-Host "No log file yet. Start the backend with .\run.ps1 first." -ForegroundColor Yellow
    exit 1
}

Write-Host "Tailing $logFile (Ctrl+C to stop)" -ForegroundColor Green
Get-Content -Path $logFile -Wait -Tail 40
