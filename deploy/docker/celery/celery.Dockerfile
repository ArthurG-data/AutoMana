FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY celery_app/. /app
RUN ls -l /app
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

CMD ["celery", "-A", "main", "worker", "-l", "INFO"]