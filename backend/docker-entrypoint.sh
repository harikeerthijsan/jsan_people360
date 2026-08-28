#!/usr/bin/env sh
# JSAN People360 API -- container start-up.
#
# 1. Apply any pending database migrations (idempotent).
# 2. Optionally create the bootstrap administrator and baseline settings
#    (idempotent; controlled by SEED_ON_START, default true).
# 3. Optionally load the demonstration data (SEED_DEMO_DATA=true).
# 4. Serve the API on $PORT.
#
# Every step is safe to repeat, so a restart or a redeploy never double-writes.
set -eu

echo "[entrypoint] applying database migrations"
alembic upgrade head

if [ "${SEED_ON_START:-true}" = "true" ]; then
  echo "[entrypoint] ensuring bootstrap administrator and settings"
  python -m app.cli.seed --sample-data
fi

if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
  echo "[entrypoint] loading demonstration data (this takes a few minutes the first time)"
  python -m app.cli.seed_demo || echo "[entrypoint] demo data failed; continuing without it"
fi

WORKERS="${WEB_CONCURRENCY:-2}"
echo "[entrypoint] starting API on port ${PORT} with ${WORKERS} worker(s)"
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --workers "${WORKERS}" \
  --proxy-headers \
  --forwarded-allow-ips "*" \
  --no-server-header
