# =============================================================================
# Code9 API (FastAPI) — multi-stage
# Stages: base -> deps -> dev | prod
# =============================================================================

ARG PYTHON_VERSION=3.11-slim

# --- base: python + системные библиотеки ---
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

# --- deps: установка зависимостей (кэшируется) ---
FROM base AS deps

COPY apps/api/pyproject.toml /app/pyproject.toml
RUN pip install --upgrade pip && pip install -e .

# --- dev: bind-mount исходников в docker-compose ---
FROM deps AS dev
ENV APP_ENV=development
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# --- prod: код уже в образе ---
FROM deps AS prod
COPY apps/api /app
ENV APP_ENV=production
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
