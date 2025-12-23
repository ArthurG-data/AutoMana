# AutoMana

AutoMana is a FastAPI backend (Postgres + Redis + optional Celery) for tracking a Magic: The Gathering collection and supporting integrations (e.g., eBay, Shopify).

## Documentation

- [docs/README.md](docs/README.md) (index)
- [API reference](docs/API.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Deployment](docs/DEPLOYMENT.md)

Backend-specific details: [backend/README.md](backend/README.md)

## Quickstart (Docker)

### Dev

```bash
docker compose -f deploy/docker-compose.dev.yml up -d --build
```

- Backend docs: http://localhost:8000/docs
- Proxy entrypoint: https://localhost/docs (self-signed certs may require bypass)

### Prod (local simulation)

Prod is designed so **only nginx** publishes ports (80/443). Postgres/Redis/Backend stay internal.

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

## Repo layout

- `backend/` — FastAPI app, services, repositories
- `deploy/` — Docker Compose + Dockerfiles
- `config/env/` — environment files (`.env.dev`, `.env.prod`, ...)
- `docs/` — documentation
- `infra/db/init/` — Postgres init SQL (extensions/roles)
