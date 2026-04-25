# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps for psycopg2 + build wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
 && rm -rf /var/lib/apt/lists/* \
 && pip install uv

# Install Python deps first for better layer caching
COPY pyproject.toml /app/pyproject.toml
COPY uv.lock /app/uv.lock
COPY src /app/src
RUN uv sync --frozen

# Security: run as non-root
RUN useradd -m appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "automana.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]