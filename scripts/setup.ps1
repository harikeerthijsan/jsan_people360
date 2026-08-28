<#
.SYNOPSIS
    One-time developer setup for JSAN People360 on Windows.

.DESCRIPTION
    Creates the backend virtual environment, installs Python and Node
    dependencies, generates .env files with a fresh SECRET_KEY, creates the
    PostgreSQL databases, applies Alembic migrations and seeds the bootstrap
    administrator.

    Safe to re-run: every step checks for existing state first.

.PARAMETER PostgresPassword
    Password for the PostgreSQL superuser. Prompted for if omitted.

.PARAMETER SkipDatabase
    Skip database creation, migration and seeding.

.EXAMPLE
    .\scripts\setup.ps1
#>
[CmdletBinding()]
param(
    [string]$PostgresUser = 'postgres',
    [string]$PostgresHost = 'localhost',
    [int]$PostgresPort = 5432,
    [securestring]$PostgresPassword,
    [switch]$SkipDatabase
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RepoRoot 'backend'
$FrontendDir = Join-Path $RepoRoot 'frontend'
$VenvPython = Join-Path $BackendDir '.venv\Scripts\python.exe'

function Write-Step { param([string]$Message) Write-Host "`n==> $Message" -ForegroundColor Cyan }
function Write-Ok { param([string]$Message) Write-Host "    $Message" -ForegroundColor Green }
function Write-Skip { param([string]$Message) Write-Host "    $Message" -ForegroundColor DarkGray }

# ---------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------
Write-Step 'Checking prerequisites'

$python = if (Get-Command py -ErrorAction SilentlyContinue) { 'py' }
          elseif (Get-Command python -ErrorAction SilentlyContinue) { 'python' }
          else { throw 'Python 3.12+ was not found on PATH. Install it from https://python.org' }

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw 'npm was not found on PATH. Install Node.js LTS from https://nodejs.org'
}
Write-Ok "python: $python"
Write-Ok "npm:    $((Get-Command npm).Source)"

# ---------------------------------------------------------------------
# Backend virtual environment
# ---------------------------------------------------------------------
Write-Step 'Creating the backend virtual environment'
if (Test-Path $VenvPython) {
    Write-Skip 'backend/.venv already exists'
} else {
    & $python -m venv (Join-Path $BackendDir '.venv')
    Write-Ok 'created backend/.venv'
}

Write-Step 'Installing Python dependencies'
& $VenvPython -m pip install --upgrade pip --quiet
& $VenvPython -m pip install -r (Join-Path $RepoRoot 'requirements.txt') --quiet
Write-Ok 'Python dependencies installed'

# ---------------------------------------------------------------------
# Environment files
# ---------------------------------------------------------------------
Write-Step 'Preparing environment files'

$backendEnv = Join-Path $BackendDir '.env'
if (Test-Path $backendEnv) {
    Write-Skip 'backend/.env already exists (left untouched)'
} else {
    $secret = & $VenvPython -c "import secrets; print(secrets.token_urlsafe(64))"
    $content = [System.IO.File]::ReadAllText((Join-Path $BackendDir '.env.example'))
    $content = $content -replace 'SECRET_KEY=.*', "SECRET_KEY=$secret"
    [System.IO.File]::WriteAllText($backendEnv, $content, (New-Object System.Text.UTF8Encoding $false))
    Write-Ok 'created backend/.env with a generated SECRET_KEY'
}

$frontendEnv = Join-Path $FrontendDir '.env.local'
if (Test-Path $frontendEnv) {
    Write-Skip 'frontend/.env.local already exists (left untouched)'
} else {
    Copy-Item (Join-Path $FrontendDir '.env.example') $frontendEnv
    Write-Ok 'created frontend/.env.local'
}

# ---------------------------------------------------------------------
# Frontend dependencies
# ---------------------------------------------------------------------
Write-Step 'Installing Node dependencies'
Push-Location $FrontendDir
try {
    npm install --no-audit --no-fund
    Write-Ok 'Node dependencies installed'
} finally {
    Pop-Location
}

# ---------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------
if ($SkipDatabase) {
    Write-Step 'Skipping database setup (-SkipDatabase)'
} else {
    Write-Step 'Setting up PostgreSQL'

    if (-not $PostgresPassword) {
        $PostgresPassword = Read-Host "PostgreSQL password for '$PostgresUser'" -AsSecureString
    }
    $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($PostgresPassword))

    $psql = Get-Command psql -ErrorAction SilentlyContinue
    if (-not $psql) {
        $candidate = Get-ChildItem 'C:\Program Files\PostgreSQL\*\bin\psql.exe' -ErrorAction SilentlyContinue |
                     Sort-Object FullName -Descending | Select-Object -First 1
        if (-not $candidate) { throw 'psql was not found. Install PostgreSQL or add its bin directory to PATH.' }
        $psqlPath = $candidate.FullName
    } else {
        $psqlPath = $psql.Source
    }
    Write-Ok "psql: $psqlPath"

    $env:PGPASSWORD = $plainPassword
    foreach ($db in @('jsan_people360', 'jsan_people360_test')) {
        $exists = & $psqlPath -U $PostgresUser -h $PostgresHost -p $PostgresPort -tAc `
            "SELECT 1 FROM pg_database WHERE datname='$db';"
        if ($exists -eq '1') {
            Write-Skip "database $db already exists"
        } else {
            & $psqlPath -U $PostgresUser -h $PostgresHost -p $PostgresPort -c "CREATE DATABASE $db;" | Out-Null
            Write-Ok "created database $db"
        }
    }

    # Record the credentials in backend/.env so the app can connect.
    $content = [System.IO.File]::ReadAllText($backendEnv)
    $content = $content -replace 'POSTGRES_USER=.*', "POSTGRES_USER=$PostgresUser"
    $content = $content -replace 'POSTGRES_PASSWORD=.*', "POSTGRES_PASSWORD=$plainPassword"
    $content = $content -replace 'POSTGRES_HOST=.*', "POSTGRES_HOST=$PostgresHost"
    $content = $content -replace 'POSTGRES_PORT=.*', "POSTGRES_PORT=$PostgresPort"
    [System.IO.File]::WriteAllText($backendEnv, $content, (New-Object System.Text.UTF8Encoding $false))
    Write-Ok 'recorded database credentials in backend/.env'

    Write-Step 'Applying migrations'
    Push-Location $BackendDir
    try {
        & $VenvPython -m alembic upgrade head
        Write-Ok 'schema is up to date'

        Write-Step 'Seeding development data'
        & $VenvPython -m app.cli.seed
    } finally {
        Pop-Location
        Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
    }
}

# ---------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------
Write-Host "`nSetup complete." -ForegroundColor Green
Write-Host @"

Start the stack with two terminals:

  Terminal 1 (API)
    cd backend
    .\.venv\Scripts\Activate.ps1
    uvicorn app.main:app --reload

  Terminal 2 (web)
    cd frontend
    npm run dev

Then open http://localhost:3000 and sign in with the bootstrap administrator
credentials from backend/.env (DEFAULT_ADMIN_EMAIL / DEFAULT_ADMIN_PASSWORD).
"@ -ForegroundColor Gray
