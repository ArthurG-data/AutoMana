# Backend (FastAPI)

This folder contains the FastAPI backend implementation.

- Repo overview + how to run everything: `../README.md`
- Documentation index: `../docs/README.md`

## Key endpoints

- Health: `GET /health`
- Swagger UI: `GET /docs`
- OpenAPI JSON: `GET /openapi.json`

## Quickstart (recommended: Docker Compose)

Run from the repo root.

### Dev

```sh
docker compose -f deploy/docker-compose.dev.yml up -d --build
```

- Backend docs: `http://localhost:8000/docs`

### Prod-style (local simulation)

Prod is designed so **only nginx** publishes ports (80/443). Backend/Postgres/Redis stay internal.

```sh
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

## Code map

- `api/` — FastAPI routers (`/api/...`)
- `new_services/` — business logic (called via `ServiceManager`)
- `repositories/` — DB and external API repositories
- `schemas/` — Pydantic models
- `core/` — settings + DB pool initialization

## More docs

- API: `../docs/API.md`
- Architecture: `../docs/ARCHITECTURE.md`
- Deployment: `../docs/DEPLOYMENT.md`
- Operations: `../docs/OPERATIONS.md`
- Troubleshooting: `../docs/TROUBLESHOOTING.md`
