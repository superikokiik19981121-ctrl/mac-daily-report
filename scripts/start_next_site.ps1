$ErrorActionPreference = "Continue"

$AppDir = Split-Path -Parent $PSScriptRoot
$NextDir = Join-Path $AppDir "next_site"
$LogDir = Join-Path $AppDir "logs"
$Port = 3003
$Url = "http://127.0.0.1:$Port"
$OutLog = Join-Path $LogDir "next-dev.out.log"
$ErrLog = Join-Path $LogDir "next-dev.err.log"

if (!(Test-Path $LogDir)) {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
}

function Write-NextLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$timestamp] $Message" | Out-File -FilePath (Join-Path $LogDir "next-site.log") -Append -Encoding utf8
}

function Add-LocalNodeToPath {
    $nodeCommand = Get-Command node -ErrorAction SilentlyContinue
    if ($nodeCommand) {
        return $nodeCommand.Source
    }

    $localNodeDir = Join-Path (Split-Path -Parent $AppDir) "agents.md\.local-tools\node-v24.15.0-win-x64"
    $localNodePath = Join-Path $localNodeDir "node.exe"
    if (Test-Path $localNodePath) {
        $env:PATH = "$localNodeDir;$localNodeDir\node_modules\corepack\shims;$env:PATH"
        return $localNodePath
    }

    throw "node.exe was not found in PATH or local tools: $localNodeDir"
}

Set-Location $NextDir
$NodePath = Add-LocalNodeToPath
$NextBin = Join-Path $NextDir "node_modules\next\dist\bin\next"

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (!$listener) {
    Write-NextLog "starting Next.js dev server on $Url"
    Start-Process `
        -FilePath $NodePath `
        -ArgumentList @($NextBin, "dev", "--webpack", "-H", "127.0.0.1", "-p", $Port) `
        -WorkingDirectory $NextDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput $OutLog `
        -RedirectStandardError $ErrLog | Out-Null
}
else {
    Write-NextLog "Next.js dev server already listening on $Url"
}

for ($i = 0; $i -lt 30; $i++) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
        if ($response.StatusCode -eq 200) {
            Write-NextLog "site ready: $Url"
            Start-Process $Url
            exit 0
        }
    }
    catch {
        Start-Sleep -Seconds 2
    }
}

Write-NextLog "site did not become ready within timeout: $Url"
Start-Process $Url
exit 1
