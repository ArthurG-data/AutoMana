# AutoMana

AutoMana is a FastAPI backend for tracking a Magic: The Gathering collection with integrations for eBay, Shopify, Scryfall, MTGJson, and MTGStock. It uses PostgreSQL (+ TimescaleDB + pgvector) for persistence, Redis for caching/queuing, and Celery for background jobs.

## Documentation

- [docs/README.md](docs/README.md) — documentation index
- [docs/API.md](docs/API.md) — API reference
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — architecture and design patterns
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — Docker Compose, env files, secrets
- [docs/LOGGING.md](docs/LOGGING.md) — structured logging
- [docs/SCRYFALL_PIPELINE.md](docs/SCRYFALL_PIPELINE.md) — Scryfall ETL pipeline
- [docs/MTGJSON_PIPELINE.md](docs/MTGJSON_PIPELINE.md) — MTGJson daily price ingestion pipeline
- [docs/MTGSTOCK_PIPELINE.md](docs/MTGSTOCK_PIPELINE.md) — MTGStocks price ingestion pipeline

## Quickstart (Docker)

### Dev

```bash
docker compose -f deploy/docker-compose.dev.yml up -d --build
```

- API docs: http://localhost:8000/docs
- Backend health: http://localhost:8000/health
- Ports: backend `8000`, postgres `5433`, redis `6379`

### Prod

Only nginx publishes ports (80/443). Postgres, Redis, and the backend stay internal.

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

## Repo layout

```
src/automana/
  api/          — FastAPI routers and schemas
  core/         — services, repositories, settings, logging, storage
  worker/       — Celery tasks and runtime
  database/     — SQL schemas and migrations
  tools/        — CLI utilities
config/
  env/          — environment files (.env.dev, .env.prod, ...)
  secrets/      — Docker secret files (not committed)
deploy/         — Docker Compose files and Dockerfiles
infra/db/init/  — Postgres init SQL (extensions, roles)
docs/           — documentation
```
