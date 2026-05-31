$ErrorActionPreference = "Stop"

$TaskName = "MacDailyReportUpdate"
$AppDir = Split-Path -Parent $PSScriptRoot
$ScriptPath = Join-Path $AppDir "scripts\update_daily.ps1"

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""

$Trigger = New-ScheduledTaskTrigger -Daily -At 6:00AM

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Update McDonald's daily report every day at 6:00 AM JST." `
    -Force | Out-Null

Write-Host "Registered scheduled task: $TaskName"
