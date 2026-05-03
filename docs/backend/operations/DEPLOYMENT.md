# Deployment

This document explains Docker, Docker Compose, container orchestration, environment configuration, and CI/CD integration for AutoMana.

**Related files:**
- `deploy/docker-compose.dev.yml` — Development environment
- `deploy/docker-compose.prod.yml` — Production environment
- `deploy/docker/` — Dockerfiles and container configs
- `docs/OPERATIONS.md` — Day-2 operations (logs, restarts, backup/restore)

---

## Docker Image Structure

AutoMana uses multi-stage Docker builds to keep images small and secure.

### Backend image (`deploy/docker/backend/Dockerfile`)

```dockerfile
# Stage 1: Builder
FROM python:3.12-slim AS builder

WORKDIR /build
RUN pip install --no-cache-dir --user poetry
COPY pyproject.toml poetry.lock ./
RUN poetry export -f requirements.txt | pip install --no-cache-dir --user -r /dev/stdin

# Stage 2: Runtime
FROM python:3.12-slim

WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY src/ ./src/
ENV PATH=/root/.local/bin:$PATH

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "automana.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Benefits:**

- **Builder stage:** Dependencies are compiled/cached
- **Runtime stage:** Final image includes only runtime files (no build tools, pip, poetry)
- **Size:** ~500MB (vs 1.5GB with everything)

### Celery worker image

Same as backend but with a different entrypoint:

```dockerfile
ENTRYPOINT ["celery", "-A", "automana.worker.app", "worker", "-l", "info"]
```

### Database image

PostgreSQL + TimescaleDB + pgvector extensions:

```dockerfile
FROM postgres:16-alpine

RUN apt-get update && apt-get install -y \
    postgresql-contrib \
    timescaledb \
    postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*

COPY infra/db/init/*.sql.tpl /docker-entrypoint-initdb.d/
```

---

## Docker Compose Configuration

AutoMana provides separate Docker Compose files for dev and prod environments.

### Development (`deploy/docker-compose.dev.yml`)

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    ports:
      - "5433:5432"  # Host can connect to localhost:5433
    environment:
      POSTGRES_DB: automana
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: dev_password  # For dev only; change in production
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  backend:
    build: deploy/docker/backend
    ports:
      - "8000:8000"
    environment:
      ENV: dev
      POSTGRES_HOST: postgres  # Inside network, use service name
      POSTGRES_PORT: 5432
      LOG_LEVEL: INFO
      LOG_JSON: 0  # Human-readable for dev
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ./src:/app/src  # Live reload in dev

  celery-worker:
    build: deploy/docker/backend
    command: celery -A automana.worker.app worker -l info
    environment:
      ENV: dev
      POSTGRES_HOST: postgres
      REDIS_HOST: redis
    depends_on:
      - postgres
      - redis

  celery-beat:
    build: deploy/docker/backend
    command: celery -A automana.worker.app beat -l info
    environment:
      ENV: dev
      POSTGRES_HOST: postgres
      REDIS_HOST: redis
    depends_on:
      - postgres
      - redis

  flower:
    image: mher/flower:2.0
    ports:
      - "5555:5555"
    environment:
      CELERY_BROKER_URL: redis://redis:6379/0
      CELERY_RESULT_BACKEND: redis://redis:6379/0

  proxy:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./deploy/docker/nginx/nginx.local.conf:/etc/nginx/nginx.conf
      - ./config/nginx/certs:/etc/nginx/certs
    depends_on:
      - backend
      - flower

volumes:
  postgres_data:
```

**Key differences from production:**

- Services publish ports directly (no isolation)
- `LOG_JSON=0` for human-readable logs
- Source code mounted as volume for live reload
- No health checks (dev is lenient)
- Flower exposed directly on port 5555

### Production (`deploy/docker-compose.prod.yml`)

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    # NO ports published (only proxy can reach it)
    environment:
      POSTGRES_DB: automana
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - /backups:/backups
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
    secrets:
      - db_password

  redis:
    image: redis:7-alpine
    # NO ports published
    command: redis-server --requirepass ${REDIS_PASSWORD}
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build: deploy/docker/backend
    # NO ports published (only proxy can reach it)
    environment:
      ENV: prod
      POSTGRES_HOST: postgres
      POSTGRES_PORT: 5432
      LOG_LEVEL: INFO
      LOG_JSON: 1  # JSON for log aggregation
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    secrets:
      - db_password
      - jwt_secret_key

  celery-worker:
    build: deploy/docker/backend
    command: celery -A automana.worker.app worker -l info --concurrency=4
    environment:
      ENV: prod
      POSTGRES_HOST: postgres
      REDIS_HOST: redis
    depends_on:
      - postgres
      - redis
    secrets:
      - db_password

  celery-beat:
    build: deploy/docker/backend
    command: celery -A automana.worker.app beat -l info
    environment:
      ENV: prod
      POSTGRES_HOST: postgres
      REDIS_HOST: redis
    depends_on:
      - postgres
      - redis
    secrets:
      - db_password

  proxy:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
      - "8080:8080"  # Tunnel endpoint (auth-exempt health check)
    volumes:
      - ./deploy/docker/nginx/nginx.prod.conf:/etc/nginx/nginx.conf
      - ./config/nginx/certs:/etc/nginx/certs
    depends_on:
      - backend

volumes:
  postgres_data:

secrets:
  db_password:
    external: true
  jwt_secret_key:
    external: true
```

**Key differences:**

- **No published ports** on internal services (database, redis, backend, celery)
- **Only proxy publishes** 80, 443, 8080 (the public entrypoint)
- **Health checks** on all services
- **Secrets** injected from Docker's secret store
- **LOG_JSON=1** for structured logging and aggregation
- **Celery concurrency** limited to 4 workers (tuned per deployment)

---

## Environment Configuration

### Env files and secrets

Development and staging configurations live in git-ignored `.env.*` files. Production secrets are stored in a secure vault (AWS Secrets Manager, HashiCorp Vault, etc.) and injected at deployment time.

**Directory structure:**

```
config/
├── env/
│   ├── .env.example      (git-tracked template)
│   ├── .env.dev          (git-ignored, dev secrets)
│   ├── .env.staging      (git-ignored, staging secrets)
│   └── .env.prod         (git-ignored, production secrets)
├── nginx/
│   ├── certs/
│   │   ├── cert.pem      (TLS certificate)
│   │   └── key.pem       (TLS private key)
│   └── nginx.conf        (optional; overrides default)
└── secrets/              (for Docker secret files in dev)
```

**Example** (`config/env/.env.example`):

```bash
# Environment
ENV=dev
APP_ENV=dev
SERVICE_NAME=backend

# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
DB_NAME=automana
APP_BACKEND_DB_USER=app_backend
DB_PASSWORD=<random-password>

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=<random-password>

# Auth
JWT_SECRET_KEY=<32-byte-base64-encoded>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15

# Logging
LOG_LEVEL=INFO
LOG_JSON=0

# API keys
EBAY_CLIENT_ID=<ebay-app-id>
EBAY_CLIENT_SECRET=<ebay-secret>
EBAY_ENVIRONMENT=sandbox
```

### Settings loading

`src/automana/core/settings.py` loads configuration from environment variables:

```python
from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Environment
    app_env: str = Field(default="dev", alias="APP_ENV")
    service_name: str = Field(default="unknown", alias="SERVICE_NAME")
    
    # Database
    db_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    db_port: int = Field(default=5432, alias="POSTGRES_PORT")
    db_name: str = Field(default="automana", alias="DB_NAME")
    db_user: str = Field(default="app_backend", alias="APP_BACKEND_DB_USER")
    db_password: str = Field(..., alias="DB_PASSWORD")
    
    # Auth
    jwt_secret_key: str = Field(..., alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=15, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    
    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_json: str = Field(default="1", alias="LOG_JSON")
    
    class Config:
        env_file = f".env.{os.getenv('ENV', 'dev')}"
        case_sensitive = True
```

**Usage:**

```python
from automana.core.settings import get_settings

settings = get_settings()
print(settings.db_host)  # "localhost" in dev, "postgres.prod" in prod
```

---

## TLS & HTTPS Setup

### Certificate acquisition

**Let's Encrypt (automatic renewal):**

```bash
# In production, use Certbot with Docker
docker run --rm -it -v /etc/letsencrypt:/etc/letsencrypt -v /var/www/certbot:/var/www/certbot \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  -d automana.example.com -d api.automana.example.com
```

**Manual certificates (for testing):**

```bash
# Generate a self-signed certificate (dev/test only)
openssl req -x509 -newkey rsa:4096 -keyout config/nginx/certs/key.pem \
  -out config/nginx/certs/cert.pem -days 365 -nodes \
  -subj "/C=US/ST=State/L=City/O=Org/CN=localhost"
```

### nginx SSL configuration

**TLS 1.3 only (production):**

```nginx
server {
    listen 443 ssl http2 default_server;
    server_name _;
    
    ssl_certificate /etc/nginx/certs/cert.pem;
    ssl_certificate_key /etc/nginx/certs/key.pem;
    
    # Force TLS 1.3 and 1.2 only (no SSLv3, TLS 1.0, 1.1)
    ssl_protocols TLSv1.2 TLSv1.3;
    
    # Strong ciphers
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305';
    ssl_prefer_server_ciphers on;
    
    # HSTS (enforce HTTPS for 1 year)
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
}
```

**Redirect HTTP to HTTPS:**

```nginx
server {
    listen 80 default_server;
    server_name _;
    
    # Allow Let's Encrypt validation
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    # Everything else redirects to HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}
```

---

## Reverse Proxy (nginx) Configuration

### Backend routing

```nginx
upstream fastapi_backend {
    server backend:8000;
    keepalive 32;  # Connection pooling
}

server {
    listen 443 ssl http2;
    server_name api.automana.example.com;
    
    location /api/ {
        proxy_pass http://fastapi_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Request-ID $request_id;
        
        # Timeouts
        proxy_connect_timeout 10s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }
    
    # WebSocket support (Flower, real-time updates)
    location /ws/ {
        proxy_pass http://fastapi_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

### Flower (Celery monitoring)

```nginx
upstream flower {
    server flower:5555;
    keepalive 4;
}

server {
    listen 443 ssl http2;
    server_name automana.example.com;
    
    location /flower/ {
        auth_basic "Flower Admin";
        auth_basic_user_file /etc/nginx/htpasswd;  # htpasswd -c htpasswd admin
        
        proxy_pass http://flower/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Rate limiting

```nginx
limit_req_zone $binary_remote_addr zone=general:10m rate=100r/s;
limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;

server {
    location /api/auth/login {
        limit_req zone=login burst=2 nodelay;
        proxy_pass http://fastapi_backend;
    }
    
    location /api/ {
        limit_req zone=general burst=50 nodelay;
        proxy_pass http://fastapi_backend;
    }
}
```

### Compression

```nginx
gzip on;
gzip_vary on;
gzip_min_length 10240;
gzip_proxied expired no-cache no-store private must-revalidate;
gzip_types
    text/plain
    text/css
    text/xml
    text/javascript
    application/json
    application/javascript
    application/xml+rss;
gzip_disable "MSIE [1-6]\.";
```

---

## Health Checks and Readiness Probes

### Application health endpoint

```python
# src/automana/api/routers/health.py

@router.get("/health", tags=["operations"])
async def health_check(request: Request) -> dict:
    """Simple health check (no database)."""
    return {"status": "ok", "service": "backend"}

@router.get("/health/ready", tags=["operations"])
async def readiness_probe(request: Request) -> dict:
    """Readiness probe (checks database and cache)."""
    try:
        # Check database
        pool = request.app.state.async_db_pool
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        
        # Check cache
        redis_client = request.app.state.redis
        await redis_client.ping()
        
        return {"status": "ready", "database": "ok", "cache": "ok"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service unavailable: {e}")
```

### Docker Compose health checks

```yaml
services:
  backend:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
  
  postgres:
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
```

### Kubernetes readiness probes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
spec:
  template:
    spec:
      containers:
      - name: backend
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 30
          failureThreshold: 3
```

---

## Rolling Deployments

### Zero-downtime deployment

1. **Build new image**
   ```bash
   docker build -t myregistry/backend:v1.2.0 -f deploy/docker/backend/Dockerfile .
   docker push myregistry/backend:v1.2.0
   ```

2. **Update Docker Compose**
   ```yaml
   backend:
     image: myregistry/backend:v1.2.0
   ```

3. **Apply with health checks**
   ```bash
   # Bring up new container with health checks
   docker compose up -d --no-deps --scale backend=2 backend
   
   # Wait for new container to be healthy
   docker compose exec -T backend curl -f http://localhost:8000/health
   
   # Remove old container
   docker compose up -d --no-deps --scale backend=1 backend
   ```

### Database migrations (zero-downtime)

AutoMana migrations are designed to be backward-compatible:

1. **Deploy new code** (which reads old schema)
2. **Run migration** (adds new columns/tables, no drops)
3. **Deploy updated code** (which uses new schema)
4. **Clean up** (remove old columns in later migration)

Example:

```sql
-- 1. Add new column (backward-compatible)
ALTER TABLE card_catalog.cards ADD COLUMN new_field TEXT DEFAULT NULL;

-- 2. Backfill (may take time; runs concurrently with app)
UPDATE card_catalog.cards SET new_field = ... WHERE new_field IS NULL;

-- 3. Later: Remove old column (once all code is updated)
ALTER TABLE card_catalog.cards DROP COLUMN old_field;
```

---

## CI/CD Pipeline Integration

### GitHub Actions example

```yaml
# .github/workflows/deploy-prod.yml

name: Deploy to Production

on:
  push:
    branches: [main]
    paths:
      - 'src/automana/**'
      - 'deploy/**'
      - 'pyproject.toml'

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - uses: docker/setup-buildx-action@v2
      
      - uses: docker/login-action@v2
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - uses: docker/build-push-action@v4
        with:
          context: .
          file: deploy/docker/backend/Dockerfile
          push: true
          tags: |
            ghcr.io/${{ github.repository }}/backend:${{ github.sha }}
            ghcr.io/${{ github.repository }}/backend:latest
          cache-from: type=registry,ref=ghcr.io/${{ github.repository }}/backend:buildcache
          cache-to: type=registry,ref=ghcr.io/${{ github.repository }}/backend:buildcache

  deploy-staging:
    runs-on: ubuntu-latest
    needs: build-and-push
    steps:
      - uses: actions/checkout@v3
      
      - name: Deploy to staging
        env:
          DEPLOY_KEY: ${{ secrets.STAGING_DEPLOY_KEY }}
          DEPLOY_HOST: staging.automana.example.com
          IMAGE_TAG: ${{ github.sha }}
        run: |
          echo "$DEPLOY_KEY" > /tmp/deploy_key
          chmod 600 /tmp/deploy_key
          ssh -i /tmp/deploy_key deploy@$DEPLOY_HOST \
            "cd /opt/automana && \
             docker pull ghcr.io/owner/automana/backend:$IMAGE_TAG && \
             IMAGE=$IMAGE_TAG docker compose -f docker-compose.prod.yml up -d --no-deps backend && \
             docker compose exec -T backend curl -f http://localhost:8000/health"

  deploy-prod:
    runs-on: ubuntu-latest
    needs: [build-and-push, deploy-staging]
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3
      
      - name: Deploy to production
        env:
          DEPLOY_KEY: ${{ secrets.PROD_DEPLOY_KEY }}
          DEPLOY_HOST: api.automana.example.com
          IMAGE_TAG: ${{ github.sha }}
        run: |
          echo "$DEPLOY_KEY" > /tmp/deploy_key
          chmod 600 /tmp/deploy_key
          ssh -i /tmp/deploy_key deploy@$DEPLOY_HOST \
            "cd /opt/automana && \
             docker pull ghcr.io/owner/automana/backend:$IMAGE_TAG && \
             IMAGE=$IMAGE_TAG docker compose -f docker-compose.prod.yml up -d --no-deps backend"
```

---

## Summary

AutoMana's deployment approach:

1. **Docker:** Multi-stage builds for small, secure images
2. **Docker Compose:** Identical configs for dev, staging, prod (only env vars differ)
3. **Secrets:** Injected at runtime, never in images or configs
4. **nginx:** Reverse proxy, TLS termination, rate limiting
5. **Health checks:** Automated restart of failing containers
6. **Migrations:** Backward-compatible for zero-downtime deployments
7. **CI/CD:** Automated testing, building, and rolling deployments

See `docs/OPERATIONS.md` for day-2 runbooks (logs, restarts, backups).
