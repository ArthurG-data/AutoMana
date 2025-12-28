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

COPY celery_app/. /app/celery_app/
COPY backend/core/. /app/backend/core/.
COPY backend/new_services/. /app/backend/new_services/.
COPY backend/shared/. /app/backend/shared/.
COPY  backend/repositories/. /app/backend/repositories/.
COPY backend/exceptions/. /app/backend/exceptions/.
COPY  backend/schemas/. /app/backend/schemas/.
COPY backend/utils/. /app/backend/utils/.

RUN ls -l /app
RUN pip install --upgrade pip && pip install -r /app/celery_app/requirements.txt

RUN addgroup --system celery && adduser --system --ingroup celery celery
USER celery

CMD ["celery", "-A", "main", "worker", "-l", "INFO"]