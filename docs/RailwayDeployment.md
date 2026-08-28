# Deploying JSAN People360 to Railway

People360 runs on Railway as **three services in one project**:

| Service | What it is | Built from |
| --- | --- | --- |
| **Postgres** | Railway's managed PostgreSQL | Railway template |
| **api** | The FastAPI backend (migrations run on every start) | `backend/Dockerfile` via `railway.api.json` |
| **web** | The Next.js client | `frontend/Dockerfile` via `railway.web.json` |

Everything the platform needs is already in the repository:

```text
railway.api.json               Railway config for the api service
railway.web.json               Railway config for the web service
backend/Dockerfile             API image (Python 3.12, uvicorn)
backend/docker-entrypoint.sh   migrate → seed admin → serve
frontend/Dockerfile            Web image (Node 22, Next.js standalone)
.dockerignore                  keeps secrets and junk out of the images
```

The whole set-up takes about fifteen minutes. Steps 1–6 are done once; after
that every push to the connected branch redeploys automatically.

---

## 1. Create the project and the database

1. In Railway, **New Project → Deploy from GitHub repo** and pick this repository.
   Railway creates one service from it; you will turn that into **api** in step 2
   and add **web** in step 4.
2. **+ New → Database → PostgreSQL**. Railway names it `Postgres` and exposes a
   `DATABASE_URL` variable you can reference from other services.

## 2. Configure the **api** service

Open the service Railway created from the repo and set, under **Settings**:

| Setting | Value |
| --- | --- |
| Service name | `api` |
| Root directory | *(leave empty — the repo root)* |
| Config-as-code file | `railway.api.json` |
| Networking → Public networking | **Generate domain** (note it, e.g. `api-production-xxxx.up.railway.app`) |

Under **Variables**, add (the *Raw editor* accepts the block below as-is):

```env
APP_ENV=production
DEBUG=false
LOG_FORMAT=json

# Database: reference the Postgres service, do not paste the URL.
DATABASE_URL=${{Postgres.DATABASE_URL}}

# Generate once:  python -c "import secrets; print(secrets.token_urlsafe(64))"
SECRET_KEY=<64+ random characters>

# Who may call this API and from where
TRUSTED_HOSTS=api-production-xxxx.up.railway.app,healthcheck.railway.app
BACKEND_CORS_ORIGINS=https://web-production-xxxx.up.railway.app
FRONTEND_BASE_URL=https://web-production-xxxx.up.railway.app

# The refresh cookie crosses between the two Railway domains, so it must be
# Secure and SameSite=None. (With one custom domain for both, "lax" also works.)
COOKIE_SECURE=true
COOKIE_SAMESITE=none

# Bootstrap administrator -- created on first start, never overwritten.
DEFAULT_ADMIN_EMAIL=admin@yourcompany.com
DEFAULT_ADMIN_PASSWORD=<a strong password, NOT Admin@12345>
DEFAULT_ADMIN_NAME=System Administrator

# Uploaded documents and payslips live on a volume (step 3).
UPLOAD_DIR=/data/uploads

# Optional
SEED_ON_START=true        # ensure admin + settings + sample org on every start (idempotent)
SEED_DEMO_DATA=false      # set true once to load the demo company, then back to false
WEB_CONCURRENCY=2         # uvicorn workers
SMTP_HOST=                # leave blank until you have a mail relay
```

> The API refuses to start in `APP_ENV=production` with a weak `SECRET_KEY`,
> the documented admin password, `COOKIE_SECURE=false`, empty `TRUSTED_HOSTS`
> or a `localhost` CORS origin. The deploy log names exactly what is wrong.
> Fill in the web domain after step 4; the API will restart cleanly once it is
> set.

## 3. Attach a volume for uploads

Documents, payslip PDFs and offer letters are files. Without a volume they
vanish on every deploy.

1. On the **api** service: **Settings → Volumes → + Add volume**.
2. Mount path: `/data/uploads` (matches `UPLOAD_DIR` above).

## 4. Add the **web** service

1. **+ New → GitHub repo → this repository** (a second service from the same repo).
2. **Settings**:

| Setting | Value |
| --- | --- |
| Service name | `web` |
| Root directory | *(empty)* |
| Config-as-code file | `railway.web.json` |
| Networking → Public networking | **Generate domain** (e.g. `web-production-xxxx.up.railway.app`) |

3. **Variables** (these are inlined into the browser bundle at build time, so a
   change requires a redeploy):

```env
NEXT_PUBLIC_API_BASE_URL=https://api-production-xxxx.up.railway.app/api/v1
NEXT_PUBLIC_APP_NAME=JSAN People360
NEXT_PUBLIC_APP_ENV=production
```

4. Go back to **api → Variables** and set `BACKEND_CORS_ORIGINS` and
   `FRONTEND_BASE_URL` to the web domain from this step.

## 5. Deploy and check

Both services build from their Dockerfiles (the first build takes 3–5 minutes).
Health checks are configured (`/api/v1/health` and `/login`), so Railway only
routes traffic once each service answers.

- API: `https://api-…/api/v1/health` returns `{"status": "ok", …}`.
- Web: open `https://web-…/login` and sign in with `DEFAULT_ADMIN_EMAIL` /
  `DEFAULT_ADMIN_PASSWORD`.

The deploy log for **api** shows the start-up sequence:

```text
[entrypoint] applying database migrations
[entrypoint] ensuring bootstrap administrator and settings
[entrypoint] starting API on port 8080 with 2 worker(s)
```

## 6. Load the demo company (optional)

Set `SEED_DEMO_DATA=true` on **api**, redeploy once, then set it back to
`false`. The demo seed takes 10–15 minutes on first run (it writes months of
attendance through the audited services); the API starts serving as soon as it
finishes. Sign-ins are listed in the README under *Demo data*.

Alternatively run it on demand from your machine with the Railway CLI:

```bash
railway link            # choose the project and the api service
railway run python -m app.cli.seed_demo
```

---

## Custom domains

Add a custom domain on each service (**Settings → Networking → Custom domain**)
and point your DNS at the target Railway shows. Then update:

- **api**: `TRUSTED_HOSTS` (add the API domain), `BACKEND_CORS_ORIGINS` and
  `FRONTEND_BASE_URL` (the web domain).
- **web**: `NEXT_PUBLIC_API_BASE_URL`.

If both live under one registrable domain (`app.example.com` and
`api.example.com`) you may set `COOKIE_SAMESITE=lax` and
`COOKIE_DOMAIN=.example.com` for a stricter cookie.

## Email

Password-reset and preboarding emails need an SMTP relay. Set `SMTP_HOST`,
`SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` on **api** (see
`docs/EnvironmentVariables.md`). With `SMTP_HOST` blank, the reset link is
written to the deploy log instead.

## Updating

Push to the connected branch. Railway rebuilds only the service whose files
changed (`watchPatterns` in the two config files) and applies migrations
automatically on start. Roll back from the deployment list if needed; migrations
are forward-only, so roll back the code only after checking the migration in
question is compatible.

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| api crashes at start with *Refusing to start: … configured for development* | One of the production guards in step 2. The message lists each missing value. |
| api log: *could not translate host name "postgres.railway.internal"* | The Postgres service is in another project/environment, or `DATABASE_URL` was pasted rather than referenced. Use `${{Postgres.DATABASE_URL}}`. |
| Sign-in works but you are logged out after 15 minutes | The refresh cookie is being dropped: `COOKIE_SECURE=true` + `COOKIE_SAMESITE=none` on **api**, and `NEXT_PUBLIC_API_BASE_URL` on **web** must be `https://`. |
| Browser console shows a CORS error | `BACKEND_CORS_ORIGINS` must be exactly the web origin (`https://…`, no trailing slash, no path). |
| 400 *Invalid host header* | Add the domain to `TRUSTED_HOSTS` (comma-separated, no scheme). Keep `healthcheck.railway.app` in the list. |
| Uploaded documents disappear after a deploy | The volume is not mounted at `/data/uploads`, or `UPLOAD_DIR` points elsewhere. |
| web build fails with *Invalid public environment configuration* | `NEXT_PUBLIC_API_BASE_URL` is missing or not an absolute URL on the **web** service. |

## Running the images locally

```bash
# from the repository root
docker build -f backend/Dockerfile -t people360-api .
docker build -f frontend/Dockerfile --build-arg NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1 -t people360-web .

docker run --rm -p 8000:8000 --env-file backend/.env -e DATABASE_URL=postgresql://postgres:postgres@host.docker.internal:5432/jsan_people360 people360-api
docker run --rm -p 3000:3000 people360-web
```
