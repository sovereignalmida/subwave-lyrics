FROM python:3.13-slim AS base

LABEL org.opencontainers.image.title="SUB/WAVE Lyrics" \
      org.opencontainers.image.description="Fullscreen synchronized lyrics display for SUB/WAVE radio stations" \
      org.opencontainers.image.source="https://github.com/sovereignalmida/subwave-lyrics" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --gid 1000 app \
    && adduser --uid 1000 --gid 1000 --disabled-password --gecos "" --home /app app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app app ./app
RUN mkdir -p /data && chown app:app /data

USER app

FROM base AS test
COPY --chown=app:app tests ./tests
CMD ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]

FROM base AS production
EXPOSE 8095
CMD ["sh", "-c", "exec uvicorn app.main:app --host ${APP_HOST:-0.0.0.0} --port ${APP_PORT:-8095} --no-access-log"]
