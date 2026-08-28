<#
.SYNOPSIS
    Run every quality gate: formatting, linting, type checks and tests.

.DESCRIPTION
    The same checks CI enforces. Run this before opening a pull request.

.PARAMETER SkipIntegration
    Skip the backend integration tests, which need a live PostgreSQL test
    database.
#>
[CmdletBinding()]
param(
    [switch]$SkipIntegration
)

$ErrorActionPreference = 'Continue'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RepoRoot 'backend'
$FrontendDir = Join-Path $RepoRoot 'frontend'
$VenvPython = Join-Path $BackendDir '.venv\Scripts\python.exe'

$failures = [System.Collections.Generic.List[string]]::new()

function Invoke-Check {
    param([string]$Name, [scriptblock]$Action)

    Write-Host "`n==> $Name" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    FAILED" -ForegroundColor Red
        $script:failures.Add($Name)
    } else {
        Write-Host "    passed" -ForegroundColor Green
    }
}

# ---------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------
Push-Location $BackendDir
try {
    Invoke-Check 'backend: black (format check)' { & $VenvPython -m black --check . }
    Invoke-Check 'backend: isort (import order)' { & $VenvPython -m isort --check-only . }
    Invoke-Check 'backend: ruff (lint)' { & $VenvPython -m ruff check . }
    # The backend half of "type checks" in the summary above. `mypy` is
    # configured strict in pyproject.toml, and for a long time nothing ran it --
    # the frontend had tsc wired into this script and into pre-commit while the
    # backend had neither, so the strictness was aspirational rather than
    # enforced. It is a gate on both now.
    Invoke-Check 'backend: mypy (types)' { & $VenvPython -m mypy app }

    $testTarget = if ($SkipIntegration) { 'tests/unit' } else { 'tests' }
    Invoke-Check "backend: pytest ($testTarget)" { & $VenvPython -m pytest $testTarget -q }
} finally {
    Pop-Location
}

# ---------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------
Push-Location $FrontendDir
try {
    Invoke-Check 'frontend: prettier (format check)' { npm run format:check }
    Invoke-Check 'frontend: tsc (types)' { npm run typecheck }
    Invoke-Check 'frontend: eslint (lint)' { npm run lint }
    Invoke-Check 'frontend: jest (tests)' { npm test }
} finally {
    Pop-Location
}

# ---------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------
Write-Host "`n----------------------------------------" -ForegroundColor Gray
if ($failures.Count -eq 0) {
    Write-Host 'All checks passed.' -ForegroundColor Green
    exit 0
}

Write-Host "$($failures.Count) check(s) failed:" -ForegroundColor Red
foreach ($failure in $failures) { Write-Host "  - $failure" -ForegroundColor Red }
exit 1
