# Installation

Detailed setup for a local development environment, plus troubleshooting.

For the short version see the [README](../README.md#quick-start).

---

## 1. Prerequisites

| Requirement | Version | Check |
| --- | --- | --- |
| Python | 3.12+ | `python --version` (Windows: `py -0p`) |
| Node.js | 20+ (LTS) | `node --version` |
| npm | 10+ | `npm --version` |
| PostgreSQL | 14+ | `psql --version` |
| Git | any recent | `git --version` |

### Windows notes

**Python.** Install from [python.org](https://www.python.org/downloads/) and tick
*Add python.exe to PATH*. Verify with `py -0p`.

**PostgreSQL.** The [EnterpriseDB installer](https://www.postgresql.org/download/windows/)
does not add `psql` to `PATH`. Add it for the current session:

```powershell
$env:Path += ';C:\Program Files\PostgreSQL\18\bin'
```

Or permanently, then restart your terminal:

```powershell
[Environment]::SetEnvironmentVariable(
  'Path',
  [Environment]::GetEnvironmentVariable('Path', 'User') + ';C:\Program Files\PostgreSQL\18\bin',
  'User')
```

Confirm the service is running:

```powershell
Get-Service -Name "postgresql*"
```

**Script execution.** If `setup.ps1` is blocked:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

---

## 2. Scripted setup (Windows)

```powershell
git clone <repository-url> jsan-people360
cd jsan-people360
.\scripts\setup.ps1
```

The script creates the virtual environment, installs both dependency sets,
writes `.env` files with a generated `SECRET_KEY`, creates both databases,
applies migrations and seeds the administrator. It is safe to re-run — every
step checks for existing state.

Skip the database portion with `.\scripts\setup.ps1 -SkipDatabase`.

---

## 3. Manual setup

### 3.1 Clone

```bash
git clone <repository-url> jsan-people360
cd jsan-people360
```

### 3.2 Backend virtual environment

```bash
# Windows
py -3.12 -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1

# macOS / Linux
python3.12 -m venv backend/.venv
source backend/.venv/bin/activate
```

Your prompt should now be prefixed with `(.venv)`.

### 3.3 Python dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3.4 Backend environment file

```bash
cp backend/.env.example backend/.env        # Windows: Copy-Item backend\.env.example backend\.env
```

Generate a secret key and paste it into `backend/.env`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

At minimum, set:

```ini
SECRET_KEY=<the generated value>
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<your password>
POSTGRES_DB=jsan_people360
```

Every variable is documented in
[`EnvironmentVariables.md`](EnvironmentVariables.md).

### 3.5 Databases

```bash
createdb jsan_people360
createdb jsan_people360_test
```

Or through `psql`:

```bash
psql -U postgres -c "CREATE DATABASE jsan_people360;"
psql -U postgres -c "CREATE DATABASE jsan_people360_test;"
```

The second database is used by the integration test suite, which builds its
schema by running the real migrations and tears it down afterwards.

### 3.6 Apply migrations

```bash
cd backend
alembic upgrade head
```

Expected output:

```
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_initial, Initial platform schema: ...
```

Verify the models and the schema agree:

```bash
alembic check
# No new upgrade operations detected.
```

### 3.7 Seed development data

```bash
python -m app.cli.seed
```

Creates the bootstrap administrator and the default application settings.
Idempotent — re-running skips what already exists.

### 3.8 Start the API

```bash
uvicorn app.main:app --reload
```

Check it:

```bash
curl http://localhost:8000/api/v1/health/ready
```

Interactive docs: <http://localhost:8000/docs>

### 3.9 Frontend

In a second terminal:

```bash
cd frontend
cp .env.example .env.local        # Windows: Copy-Item .env.example .env.local
npm install
npm run dev
```

Open <http://localhost:3000> and sign in.

---

## 4. Verify the installation

```powershell
.\scripts\verify.ps1
```

Or individually:

```bash
# Backend (from backend/, venv active)
pytest tests/unit -q      # no database needed
pytest -q                 # includes integration tests
black --check . && isort --check-only . && ruff check .

# Frontend (from frontend/)
npm run typecheck
npm run lint
npm test
npm run build
```

Expected: **102 backend tests** and **60 frontend tests** passing, and a clean
production build.

If the test database is unreachable, the integration tests **skip** rather than
fail, and the message tells you how to create it.

---

## 5. Optional: pre-commit hooks

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files      # first run, checks everything
```

These enforce formatting, linting and one guard rail: any commit reintroducing
`Base.metadata.create_all()` is rejected, because it would let the database drift
away from the migration history.

---

## 6. Daily workflow

```powershell
.\scripts\dev.ps1        # starts both servers in separate windows
```

Or manually, in two terminals:

```bash
# Terminal 1
cd backend && .venv\Scripts\Activate.ps1 && uvicorn app.main:app --reload

# Terminal 2
cd frontend && npm run dev
```

| Service | URL |
| --- | --- |
| Web app | <http://localhost:3000> |
| API | <http://localhost:8000> |
| API docs | <http://localhost:8000/docs> |
| Health | <http://localhost:8000/api/v1/health/ready> |

---

## 7. Troubleshooting

### `SECRET_KEY: Field required` on startup

`backend/.env` is missing or has no `SECRET_KEY`. Copy the template and generate
one (§3.4).

### `String should have at least 32 characters`

`SECRET_KEY` is too short. Generate a proper one.

### `value is not a valid email address` on startup

`DEFAULT_ADMIN_EMAIL` or `EMAIL_FROM` uses a reserved domain. `.local`, `.test`,
`.invalid` and bare `localhost` are special-use names and are **not** valid email
domains. Use a real domain, or the RFC 2606 reserved `example.com`.

### `connection refused` / `could not connect to server`

The server is not running or the `POSTGRES_*` values are wrong.

```powershell
Get-Service -Name "postgresql*"          # Windows
sudo systemctl status postgresql          # Linux
brew services list                        # macOS
```

### `password authentication failed for user "postgres"`

Wrong password in `backend/.env`. Test it directly:

```bash
psql -U postgres -h localhost -c "SELECT 1;"
```

### `database "jsan_people360" does not exist`

Create it (§3.5).

### `relation "users" does not exist`

Migrations have not been applied. `cd backend && alembic upgrade head`.

### `ModuleNotFoundError: No module named 'app'`

Either the virtual environment is not active, or you are not in `backend/`.
Backend commands run from `backend/` with `(.venv)` in the prompt.

### `pip install` fails building a wheel

Your Python version has no prebuilt wheel for a pinned package, so pip tries to
compile from source and needs a C/Rust toolchain. The pinned set in
`requirements.txt` has wheels for current Python releases; if you hit this on a
very new interpreter, install a slightly older Python or bump the affected pins.

### CORS errors in the browser console

The frontend origin is missing from `BACKEND_CORS_ORIGINS`. It must include the
scheme and port, with no trailing slash:

```ini
BACKEND_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

Restart the API afterwards. Note `localhost` and `127.0.0.1` are distinct
origins to a browser.

### Signed in, but reloading logs me out

The refresh cookie is being rejected. Over plain HTTP, `COOKIE_SECURE` must be
`false`. Over HTTPS across different sites you need `COOKIE_SECURE=true` **and**
`COOKIE_SAMESITE=none`.

### Password reset emails never arrive

Expected in development: with `SMTP_HOST` empty, the message is written to the
API log instead. The reset link is also returned in the API response outside
production, and the UI surfaces it on the forgot-password screen.

### `Invalid public environment configuration` in the frontend

`frontend/.env.local` is missing or `NEXT_PUBLIC_API_BASE_URL` is not an absolute
URL. It must include the scheme **and** the `/api/v1` prefix.

### Frontend changes to `.env.local` have no effect

`NEXT_PUBLIC_*` values are inlined at build time. Restart `npm run dev`, or
rebuild for production.

### Port already in use

```powershell
# Windows — find and stop whatever holds the port
Get-NetTCPConnection -LocalPort 8000 -State Listen |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

```bash
# macOS / Linux
lsof -ti:8000 | xargs kill -9
```

Or run on another port: `uvicorn app.main:app --reload --port 8001`
(then update `NEXT_PUBLIC_API_BASE_URL` to match).

### Integration tests skip

Intentional when the test database is unreachable. Create it with
`createdb jsan_people360_test`, or point `TEST_DATABASE_URL` elsewhere:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/jsan_people360_test pytest
```

### VS Code reports unresolved imports

Select the project interpreter: **Ctrl+Shift+P** → *Python: Select Interpreter* →
`./backend/.venv/Scripts/python.exe`. The workspace settings in `.vscode/` point
there by default.

---

## 8. Starting over

To rebuild the database from scratch:

```bash
cd backend
alembic downgrade base      # drop every table
alembic upgrade head        # recreate
python -m app.cli.seed      # reseed
```

To reset dependencies:

```bash
# Backend
rm -rf backend/.venv
# then repeat §3.2 and §3.3

# Frontend
rm -rf frontend/node_modules frontend/.next
cd frontend && npm install
```
