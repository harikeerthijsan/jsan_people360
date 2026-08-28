# syntax=docker/dockerfile:1.7
# JSAN People360 -- API image.
#
# Build context is the REPOSITORY ROOT (the dependency list lives there):
#   docker build -f backend/Dockerfile -t people360-api .
#
# On Railway this is selected by railway.api.json (dockerfilePath), so nothing
# needs to be typed by hand.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# libpq is not needed (asyncpg is pure wheels), but curl gives the container a
# way to probe its own health and tzdata keeps IST date maths honest.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, so a code change does not reinstall the world.
COPY requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

# The application: alembic config + migrations + package.
COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY backend/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && useradd --create-home --uid 1000 app \
    && mkdir -p /data/uploads \
    && chown -R app:app /app /data

USER app

# Railway injects PORT; 8000 is the fallback for a local `docker run`.
ENV PORT=8000 \
    UPLOAD_DIR=/data/uploads
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/api/v1/health" || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
