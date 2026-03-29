# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/pyproject.toml
COPY src /app/src
RUN RUN uv sync --frozen

RUN useradd -m appuser
USER appuser

CMD ["celery", "-A", "automana.worker.main:app", "worker", "-P", "solo", "--loglevel=INFO", "--concurrency=1"]
