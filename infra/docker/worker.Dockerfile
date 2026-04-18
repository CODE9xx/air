# =============================================================================
# Code9 Worker (RQ) — multi-stage
# =============================================================================

ARG PYTHON_VERSION=3.11-slim

FROM python:${PYTHON_VERSION} AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

FROM base AS deps
COPY apps/worker/pyproject.toml /app/pyproject.toml
RUN pip install --upgrade pip && pip install -e .

FROM deps AS dev
ENV APP_ENV=development
CMD ["python", "-m", "worker.main"]

FROM deps AS prod
COPY apps/worker /app
ENV APP_ENV=production
CMD ["python", "-m", "worker.main"]
