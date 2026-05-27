# syntax=docker/dockerfile:1.7
# ─── Builder ─────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-warn-script-location .

# ─── Runtime ─────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PATH="/install/bin:$PATH" \
    PYTHONPATH="/install/lib/python3.11/site-packages"

WORKDIR /app

# Non-root user
RUN groupadd --system app && useradd --system --gid app --create-home app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /install
COPY --chown=app:app . /app

USER app
EXPOSE 8080

# Single uvicorn worker — Cloud Run scales horizontally per instance.
# Async event loop handles concurrency within the instance.
CMD ["sh", "-c", "alembic upgrade head && python -m app.core.seed && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
