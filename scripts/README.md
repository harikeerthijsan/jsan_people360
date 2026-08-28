# Developer scripts

PowerShell scripts for the Windows development environment. Run them from the
repository root.

| Script | Purpose |
| --- | --- |
| `setup.ps1` | One-time setup: virtual environment, dependencies, `.env` files, databases, migrations, seed data. Safe to re-run. |
| `dev.ps1` | Start the API and web client in separate terminals. |
| `verify.ps1` | Run every quality gate — format, lint, types, tests. |

## Usage

```powershell
# First-time setup (prompts for the PostgreSQL password)
.\scripts\setup.ps1

# Skip database work if you already have a schema
.\scripts\setup.ps1 -SkipDatabase

# Start both servers
.\scripts\dev.ps1

# Start just one
.\scripts\dev.ps1 -ApiOnly
.\scripts\dev.ps1 -WebOnly

# Run all checks before a pull request
.\scripts\verify.ps1

# Skip tests that need a live database
.\scripts\verify.ps1 -SkipIntegration
```

## If a script will not run

PowerShell blocks unsigned scripts by default. Allow them for the current
session only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## macOS / Linux

These scripts are Windows-specific. The equivalent commands are documented in
[`../docs/Installation.md`](../docs/Installation.md) and work on any platform.
