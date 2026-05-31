$ErrorActionPreference = "Continue"

$AppDir = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $AppDir "logs"
$LogFile = Join-Path $LogDir "daily_update.log"
$NextStartScript = Join-Path $AppDir "scripts\start_next_site.ps1"

if (!(Test-Path $LogDir)) {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
}

Set-Location $AppDir

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$timestamp] daily-update start" | Out-File -FilePath $LogFile -Append -Encoding utf8

try {
    .\.venv\Scripts\python.exe main.py daily-update 2>&1 | Out-File -FilePath $LogFile -Append -Encoding utf8
    $exitCode = $LASTEXITCODE
    if ($exitCode -eq 0) {
        powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$NextStartScript" 2>&1 | Out-File -FilePath $LogFile -Append -Encoding utf8
        $nextExitCode = $LASTEXITCODE
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        "[$timestamp] next-site start/open exit_code=$nextExitCode" | Out-File -FilePath $LogFile -Append -Encoding utf8
    }
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$timestamp] daily-update end exit_code=$exitCode" | Out-File -FilePath $LogFile -Append -Encoding utf8
    exit $exitCode
}
catch {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$timestamp] daily-update failed: $($_.Exception.Message)" | Out-File -FilePath $LogFile -Append -Encoding utf8
    exit 1
}
