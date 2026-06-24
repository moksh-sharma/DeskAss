# Start the Cache AI Assistant backend using the project virtual environment.
param(
    [switch]$NoTail
)

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
$logPath = Join-Path $PSScriptRoot "logs\backend.log"

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
    if ($procId -gt 0) {
        Write-Host "Stopping stale backend PID $procId..." -ForegroundColor Yellow
        cmd /c "taskkill /F /PID $procId 2>nul" | Out-Null
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
}
Start-Sleep -Seconds 2

function Start-LiveLogForwarder {
    param([string]$Path)

    New-Item -ItemType Directory -Force -Path (Split-Path $Path) | Out-Null
    if (-not (Test-Path $Path)) {
        "" | Out-File -FilePath $Path -Encoding utf8
    }

    # Tail only lines written after this job starts (reload workers log to the file reliably).
    $tailJob = Start-Job -ScriptBlock {
        param($p)
        Get-Content -LiteralPath $p -Wait -Tail 0
    } -ArgumentList $Path

    $runspace = [runspacefactory]::CreateRunspace()
    $runspace.Open()
    $ps = [powershell]::Create()
    $ps.Runspace = $runspace
    [void]$ps.AddScript({
        param($job)
        while ($true) {
            $lines = Receive-Job $job -ErrorAction SilentlyContinue
            if ($lines) {
                foreach ($line in @($lines)) {
                    if ($null -ne $line -and "$line".Length -gt 0) {
                        [Console]::WriteLine("$line")
                    }
                }
            }
            if ($job.State -ne "Running") {
                $rest = Receive-Job $job -ErrorAction SilentlyContinue
                if ($rest) {
                    foreach ($line in @($rest)) {
                        if ($null -ne $line -and "$line".Length -gt 0) {
                            [Console]::WriteLine("$line")
                        }
                    }
                }
                break
            }
            Start-Sleep -Milliseconds 75
        }
    }).AddArgument($tailJob)
    $handle = $ps.BeginInvoke()

    return @{
        Job      = $tailJob
        PS       = $ps
        Handle   = $handle
        Runspace = $runspace
    }
}

function Stop-LiveLogForwarder {
    param($Forwarder)

    if (-not $Forwarder) { return }

    Stop-Job $Forwarder.Job -ErrorAction SilentlyContinue
    Remove-Job $Forwarder.Job -Force -ErrorAction SilentlyContinue

    if ($Forwarder.PS) {
        $Forwarder.PS.Stop()
        $Forwarder.PS.Dispose()
    }
    if ($Forwarder.Runspace) {
        $Forwarder.Runspace.Close()
        $Forwarder.Runspace.Dispose()
    }
}

Write-Host "Starting backend on http://127.0.0.1:$port" -ForegroundColor Green
if ($NoTail) {
    Write-Host "Live log tail disabled (-NoTail). File: .\logs\backend.log" -ForegroundColor DarkGray
} else {
    Write-Host "Live app logs stream below (uvicorn + .\logs\backend.log). Alt: .\tail-logs.ps1" -ForegroundColor DarkGray
}

$env:PYTHONUNBUFFERED = "1"
$env:PYTHONIOENCODING = "utf-8"

$forwarder = $null
if (-not $NoTail) {
    $forwarder = Start-LiveLogForwarder -Path $logPath
}

try {
    & $python -u -m uvicorn app.main:app --reload --port $port --log-level info --access-log
} finally {
    Stop-LiveLogForwarder -Forwarder $forwarder
}
