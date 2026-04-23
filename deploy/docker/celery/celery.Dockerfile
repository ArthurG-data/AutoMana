# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
 && rm -rf /var/lib/apt/lists/* \
 && pip install uv

COPY pyproject.toml /app/pyproject.toml
COPY uv.lock /app/uv.lock
COPY src/automana/core /app/src/automana/core
COPY src/automana/worker /app/src/automana/worker
# `database/SQL/maintenance/` contains read-only sanity-check scripts
# that the ops integrity-check repository loads via pathlib at import
# time (see `core/repositories/ops/integrity_check_sql.py`). Without
# this the module fails to import and no services register.
COPY src/automana/database /app/src/automana/database
RUN uv sync --frozen --no-install-project

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src"

RUN useradd -m appuser
RUN mkdir -p /home/appuser/flower && chown appuser:appuser /home/appuser/flower 
USER appuser

CMD ["celery", "-A", "automana.worker.main:app", "worker", "-P", "solo", "--loglevel=INFO", "--concurrency=1"]
