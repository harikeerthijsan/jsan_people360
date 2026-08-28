# Environment variables

Configuration is read from the environment, validated by Pydantic on the backend
and Zod on the frontend. Both fail loudly at startup rather than surfacing an
`undefined` deep in a request.

| File | Purpose | Committed? |
| --- | --- | --- |
| `backend/.env.example` | Backend template | Yes |
| `backend/.env` | Backend actual values | **No** |
| `frontend/.env.example` | Frontend template | Yes |
| `frontend/.env.local` | Frontend actual values | **No** |

```powershell
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env.local
```

---

## Backend

### Application

| Variable | Default | Description |
| --- | --- | --- |
| `APP_NAME` | `JSAN People360` | Shown in docs, logs and emails |
| `APP_ENV` | `local` | `local` \| `development` \| `staging` \| `production` \| `test`. Controls doc exposure, HSTS and whether reset tokens are echoed |
| `APP_VERSION` | `0.1.0` | Reported by the health endpoints |
| `JP360_DEBUG` | `false` | Includes exception detail in 500 responses. **Never true in production** |
| `API_V1_PREFIX` | `/api/v1` | Mount point for v1 routes |

### Security — required

| Variable | Default | Description |
| --- | --- | --- |
| `SECRET_KEY` | *(none — required)* | Signs access tokens. Minimum 32 characters. **Unique per environment** |
| `JWT_ALGORITHM` | `HS256` | Signing algorithm |
| `JWT_ISSUER` | `jsan-people360` | `iss` claim, validated on decode |
| `JWT_AUDIENCE` | `jsan-people360-api` | `aud` claim, validated on decode |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access token lifetime (1–1440) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token lifetime (1–90); ×4 with "keep me signed in" |
| `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES` | `30` | Reset link validity (5–1440) |
| `MAX_FAILED_LOGIN_ATTEMPTS` | `5` | Failures before lockout |
| `ACCOUNT_LOCKOUT_MINUTES` | `15` | Lockout duration |
| `BCRYPT_ROUNDS` | `12` | Password-hash work factor. Keep at 12 or higher outside automated tests |

Generate a key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

> Rotating `SECRET_KEY` invalidates every issued access token. Refresh tokens
> are opaque and unaffected, so users recover on their next refresh.

### Refresh token cookie

| Variable | Default | Description |
| --- | --- | --- |
| `REFRESH_COOKIE_NAME` | `jp360_refresh_token` | Cookie name |
| `REFRESH_COOKIE_PATH` | `/api/v1/auth` | Scope. Keeps the cookie off unrelated requests |
| `COOKIE_DOMAIN` | *(empty)* | Leave empty for host-only. Set for subdomain sharing |
| `COOKIE_SECURE` | `false` | HTTPS-only. **`true` in production** |
| `COOKIE_SAMESITE` | `lax` | `lax` \| `strict` \| `none`. Cross-site needs `none` **and** `COOKIE_SECURE=true` |

Choosing values:

| Deployment | `COOKIE_SECURE` | `COOKIE_SAMESITE` |
| --- | --- | --- |
| Local HTTP, both on `localhost` | `false` | `lax` |
| Same site over HTTPS (`app.example.com` + `api.example.com`) | `true` | `lax` |
| Different sites over HTTPS | `true` | `none` |

### Database

| Variable | Default | Description |
| --- | --- | --- |
| `POSTGRES_HOST` | `localhost` | Server host |
| `POSTGRES_PORT` | `5432` | Server port |
| `POSTGRES_USER` | `postgres` | Username |
| `POSTGRES_PASSWORD` | `postgres` | Password |
| `POSTGRES_DB` | `jsan_people360` | Database name |
| `DATABASE_URL` | *(derived)* | Full async DSN. **Overrides the `POSTGRES_*` values when set** |
| `DB_ECHO` | `false` | Log every statement. Development only |
| `DB_POOL_SIZE` | `10` | Persistent pooled connections |
| `DB_MAX_OVERFLOW` | `20` | Extra connections under load |
| `DB_POOL_TIMEOUT` | `30` | Seconds to wait for a connection |
| `DB_POOL_RECYCLE` | `1800` | Recycle connections after N seconds |

`DATABASE_URL` must use the async driver:

```
postgresql+asyncpg://user:password@host:5432/database
```

> Size the pool against your server's `max_connections`. With four workers,
> `DB_POOL_SIZE=10` and `DB_MAX_OVERFLOW=20`, peak usage is
> `4 × (10 + 20) = 120` connections.

### CORS

| Variable | Default | Description |
| --- | --- | --- |
| `BACKEND_CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated allowed browser origins |

Origins must include the scheme and any non-default port, and must not have a
trailing slash. Wildcards are not usable here: the API sends credentials, and
browsers reject `Access-Control-Allow-Origin: *` on credentialed requests.

### Logging

| Variable | Default | Description |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | `CRITICAL` \| `ERROR` \| `WARNING` \| `INFO` \| `DEBUG` |
| `LOG_FORMAT` | `console` | `console` for humans, `json` for log shippers |
| `LOG_REQUEST_BODY` | `false` | Reserved. Leave `false` — bodies contain credentials |

### Uploads

| Variable | Default | Description |
| --- | --- | --- |
| `UPLOAD_DIR` | `<repo>/uploads` | Runtime file storage. Created at startup |
| `MAX_UPLOAD_SIZE_MB` | `10` | Per-file limit (1–1024) |

### Email

| Variable | Default | Description |
| --- | --- | --- |
| `SMTP_HOST` | *(empty)* | **Leave empty in development** — emails are written to the log instead |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` | *(empty)* | SMTP username |
| `SMTP_PASSWORD` | *(empty)* | SMTP password |
| `SMTP_TLS` | `true` | Use STARTTLS |
| `EMAIL_FROM` | `no-reply@example.com` | Sender address. Validated as an email |
| `EMAIL_FROM_NAME` | `JSAN People360` | Sender display name |

### Frontend link building

| Variable | Default | Description |
| --- | --- | --- |
| `FRONTEND_BASE_URL` | `http://localhost:3000` | Used to build password reset links. Must match the deployed frontend or links will 404 |

### Bootstrap administrator

| Variable | Default | Description |
| --- | --- | --- |
| `DEFAULT_ADMIN_EMAIL` | `admin@example.com` | Seeded account. Validated as an email |
| `DEFAULT_ADMIN_PASSWORD` | `Admin@12345` | Seeded password |
| `DEFAULT_ADMIN_NAME` | `System Administrator` | Seeded display name |

Used only by `python -m app.cli.seed`, which is idempotent and never overwrites
an existing account unless `--reset-admin-password` is passed.

> **These are development credentials.** Change them before anyone else can
> reach the application.

> **Reserved domains are rejected.** `DEFAULT_ADMIN_EMAIL` and `EMAIL_FROM` are
> validated as real email addresses, and `.local`, `.test`, `.invalid` and bare
> `localhost` are special-use names that are *not* valid email domains. An
> address like `admin@company.local` will fail at startup — which is far better
> than seeding an account nobody can sign in to.

---

## Frontend

Only `NEXT_PUBLIC_*` variables reach the browser, and Next.js inlines them at
**build time**. Changing one requires a rebuild, not just a restart.

| Variable | Default | Description |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000/api/v1` | Backend base URL **including** the version prefix. Must be absolute |
| `NEXT_PUBLIC_APP_NAME` | `JSAN People360` | Browser tab, sidebar and sign-in card |
| `NEXT_PUBLIC_APP_ENV` | `local` | `local` \| `development` \| `staging` \| `production`. Drives the environment badge and whether raw error text is shown |

> **Never put a secret behind `NEXT_PUBLIC_`.** The value is compiled into
> JavaScript that every visitor downloads. Secrets belong to the backend.

---

## Production checklist

Before exposing the application:

**Backend**

- [ ] `SECRET_KEY` — unique, ≥64 random characters, from a secrets manager
- [ ] `APP_ENV=production` (disables `/docs`, `/redoc`, `/openapi.json`)
- [ ] `JP360_DEBUG=false`
- [ ] `LOG_FORMAT=json`, `LOG_LEVEL=INFO`
- [ ] `DB_ECHO=false`
- [ ] `COOKIE_SECURE=true`, `COOKIE_SAMESITE` correct for your topology
- [ ] `BACKEND_CORS_ORIGINS` lists only real frontend origins
- [ ] `DATABASE_URL` points at production; the app user is **not** a superuser
- [ ] `FRONTEND_BASE_URL` matches the deployed frontend
- [ ] SMTP configured (otherwise password reset emails only reach the log)
- [ ] `DEFAULT_ADMIN_PASSWORD` changed, or the seed account removed
- [ ] `UPLOAD_DIR` on durable storage, not the container filesystem
- [ ] `TRUSTED_HOSTS` lists the hostnames the API answers to
- [ ] `RATE_LIMIT_ENABLED=true` (see the note below on multi-worker deployments)
- [ ] `MAX_REQUEST_BODY_MB` sized above `MAX_UPLOAD_SIZE_MB`

> **Most of this list is now enforced rather than trusted.** A process started
> with `APP_ENV=production` validates these at import and **refuses to boot**
> if `SECRET_KEY` is a placeholder, `JP360_DEBUG` or `LOG_REQUEST_BODY` is on,
> `COOKIE_SECURE` is off, `TRUSTED_HOSTS` is empty, `BACKEND_CORS_ORIGINS`
> contains a wildcard or a localhost origin, or either bootstrap credential is
> still the documented default. The error names every problem at once, so a
> misconfigured deploy is fixed in one pass rather than one restart at a time.
> See `Settings._reject_unsafe_production_configuration`.

### Rate limiting

`RATE_LIMIT_*` throttles **failed** attempts per client address on the
credential endpoints only — login, forgot-password, reset-password, refresh. A
successful sign-in clears that client's count, so an office behind a single NAT
gateway is never affected while a client guessing passwords is stopped quickly.
This complements per-account lockout (`MAX_FAILED_LOGIN_ATTEMPTS`), which
cannot see one client trying a thousand different accounts once each.

It is held **in process memory**. With N workers the effective limit is N times
`RATE_LIMIT_ATTEMPTS`, and a restart forgets. That is adequate for a single-node
deployment and is not a substitute for throttling at the edge on a cluster.

**Frontend**

- [ ] `NEXT_PUBLIC_API_BASE_URL` is the production HTTPS URL
- [ ] `NEXT_PUBLIC_APP_ENV=production`
- [ ] Rebuilt after any variable change

**Platform**

- [ ] TLS terminated in front of both services
- [ ] `alembic upgrade head` runs as a deploy step, before traffic is admitted
- [ ] Database backups configured and a restore tested
- [ ] Rate limiting at the gateway (the app has none — see
      [Architecture § Known gaps](Architecture.md#12-known-gaps))
- [ ] Log aggregation collecting stdout

---

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `SECRET_KEY: Field required` at startup | No `backend/.env`, or the key is missing |
| `String should have at least 32 characters` | `SECRET_KEY` too short |
| `value is not a valid email address` at startup | `DEFAULT_ADMIN_EMAIL` or `EMAIL_FROM` uses a reserved domain such as `.local` |
| Browser blocks requests with a CORS error | Frontend origin absent from `BACKEND_CORS_ORIGINS`, or a trailing slash |
| Sign-in works, but the session is lost on reload | Refresh cookie rejected — check `COOKIE_SECURE` / `COOKIE_SAMESITE` against your scheme |
| `Invalid public environment configuration` | `NEXT_PUBLIC_API_BASE_URL` missing or not an absolute URL |
| Reset emails never arrive | `SMTP_HOST` empty — by design in development; check the API log for the message |
| Reset links point at the wrong host | `FRONTEND_BASE_URL` not updated |
| `connection refused` to PostgreSQL | Server not running, or `POSTGRES_*` values wrong |
