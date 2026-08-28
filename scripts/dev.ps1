<#
.SYNOPSIS
    Start the API and the web client together for local development.

.DESCRIPTION
    Launches uvicorn (with reload) and next dev in separate PowerShell windows
    so each keeps its own readable log stream.

.PARAMETER ApiOnly
    Start only the backend.

.PARAMETER WebOnly
    Start only the frontend.
#>
[CmdletBinding()]
param(
    [switch]$ApiOnly,
    [switch]$WebOnly
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RepoRoot 'backend'
$FrontendDir = Join-Path $RepoRoot 'frontend'

if (-not (Test-Path (Join-Path $BackendDir '.venv\Scripts\python.exe'))) {
    throw 'Backend virtual environment not found. Run .\scripts\setup.ps1 first.'
}
if (-not (Test-Path (Join-Path $FrontendDir 'node_modules'))) {
    throw 'Frontend dependencies not installed. Run .\scripts\setup.ps1 first.'
}

if (-not $WebOnly) {
    Write-Host 'Starting API on http://localhost:8000 ...' -ForegroundColor Cyan
    Start-Process powershell -ArgumentList @(
        '-NoExit', '-Command',
        "Set-Location '$BackendDir'; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --port 8000"
    )
}

if (-not $ApiOnly) {
    Write-Host 'Starting web client on http://localhost:3000 ...' -ForegroundColor Cyan
    Start-Process powershell -ArgumentList @(
        '-NoExit', '-Command',
        "Set-Location '$FrontendDir'; npm run dev"
    )
}

Write-Host @"

  API docs : http://localhost:8000/docs
  Web app  : http://localhost:3000

Close the spawned windows to stop the servers.
"@ -ForegroundColor Gray
