# Documentation Index

This is the master navigation index for AutoMana documentation. Docs are organized into category subfolders. The two root-level files that remain here are auto-generated or role-specific:

- [`PIPELINE_TECHNICAL_DEBT.md`](PIPELINE_TECHNICAL_DEBT.md) — **auto-generated** by `/pipeline-health-check` skill; live feed of pipeline metric errors and warnings
- [`MASTER_TECHNICAL_DEBT.md`](MASTER_TECHNICAL_DEBT.md) — consolidated technical debt backlog across all layers (API, services, pipelines, infrastructure, testing)

---

## Architecture

System design, patterns, and request flows.

| Document | Description |
|----------|-------------|
| [`architecture/ARCHITECTURE.md`](architecture/ARCHITECTURE.md) | Layered architecture, request flows (HTTP + Celery), integrations, known sharp edges |
| [`architecture/ARCHITECTURE_MASTER.md`](architecture/ARCHITECTURE_MASTER.md) | System overview diagram, data residency map, cross-system data flows, doc navigator |
| [`architecture/BACKEND.md`](architecture/BACKEND.md) | Backend guide — nav index to `docs/backend/` deeper dives |
| [`architecture/DESIGN_PATTERNS.md`](architecture/DESIGN_PATTERNS.md) | Glossary of all 22 design patterns used in the codebase, with file locations and rationale |

Deeper architecture dives (more verbose tutorials): `docs/backend/architecture/`

---

## API

HTTP endpoints and API-layer technical debt.

| Document | Description |
|----------|-------------|
| [`api/API.md`](api/API.md) | Endpoint reference — auth, catalog, integrations, ops/integrity |
| [`api/API_LAYER_BACKLOG.md`](api/API_LAYER_BACKLOG.md) | Senior-level bug and debt review of `src/automana/api/` (2026-05-22) |

---

## Pipelines

ETL pipeline guides — one doc per pipeline.

| Document | Description |
|----------|-------------|
| [`pipelines/SCRYFALL_PIPELINE.md`](pipelines/SCRYFALL_PIPELINE.md) | Scryfall daily ETL — 11 steps, idempotent run_key, storage management |
| [`pipelines/MTGJSON_PIPELINE.md`](pipelines/MTGJSON_PIPELINE.md) | MTGJson daily price ingestion — 6 steps, streaming COPY approach |
| [`pipelines/MTGSTOCK_PIPELINE.md`](pipelines/MTGSTOCK_PIPELINE.md) | MTGStocks price ingestion — 4 stages, 5-table dimension chain |
| [`pipelines/MTGSTOCK_REJECT_ANALYSIS.md`](pipelines/MTGSTOCK_REJECT_ANALYSIS.md) | Analysis of 5.8M unresolved staging reject rows and fix progress |

Deeper pipeline tutorials: `docs/backend/integrations/`

---

## Infrastructure

Deployment, database, caching, logging, and roles.

| Document | Description |
|----------|-------------|
| [`infrastructure/DEPLOYMENT.md`](infrastructure/DEPLOYMENT.md) | Docker Compose dev/prod, env files, nginx, VPS tunnel relay, CI/CD |
| [`infrastructure/DATABASE_ROLES.md`](infrastructure/DATABASE_ROLES.md) | PostgreSQL RBAC — role hierarchy, per-service DB users, grants |
| [`infrastructure/LOGGING.md`](infrastructure/LOGGING.md) | Structured logging — configure_logging(), JSON format, context variables, usage patterns |
| [`infrastructure/CACHING.md`](infrastructure/CACHING.md) | Redis caching architecture — cache service API, decorators, invalidation patterns, limitations |
| [`infrastructure/CACHE_MIGRATION_SUMMARY.md`](infrastructure/CACHE_MIGRATION_SUMMARY.md) | Historical: async Redis migration (PR #191) — background, decisions, future improvements |

---

## Operations

Monitoring, metrics, health, runbooks, CLI tools.

| Document | Description |
|----------|-------------|
| [`operations/OPERATIONS.md`](operations/OPERATIONS.md) | Runbook — logs, restarts, backup/restore, cert rotation |
| [`operations/TROUBLESHOOTING.md`](operations/TROUBLESHOOTING.md) | Common issues and fixes |
| [`operations/CLI_RUN_SERVICE.md`](operations/CLI_RUN_SERVICE.md) | `automana-run` CLI and `automana-tui` TUI — running services manually |
| [`operations/METRICS_REGISTRY.md`](operations/METRICS_REGISTRY.md) | MetricRegistry API — Severity, Threshold, MetricResult, MetricConfig |
| [`operations/METRICS_REPORTING.md`](operations/METRICS_REPORTING.md) | Metrics reporting service — real-time, hourly aggregation, weekly Discord reports |
| [`operations/HEALTH_METRICS.md`](operations/HEALTH_METRICS.md) | Database health metrics — card_catalog.* and pricing.* families, on-demand Scryfall audit |

---

## Testing

Test plans, manual flows, and known blockers.

| Document | Description |
|----------|-------------|
| [`testing/UNIT_TEST_PLAN.md`](testing/UNIT_TEST_PLAN.md) | Unit test plan — service inventory, coverage targets (by tier), phased rollout, known bugs |
| [`testing/TESTING_API_FLOW.md`](testing/TESTING_API_FLOW.md) | Manual API testing — throwaway user pattern, bcrypt hash, cleanup procedure |

---

## Domain Knowledge

| Document | Description |
|----------|-------------|
| [`domain/MTG_FINANCE_KNOWLEDGE_BASE.md`](domain/MTG_FINANCE_KNOWLEDGE_BASE.md) | MTG finance — global price sources, strategies, arbitrage patterns (US/CA/EU/JP/AU) |

---

## Frontend

| Document | Description |
|----------|-------------|
| [`frontend/FRONTEND.md`](frontend/FRONTEND.md) | React SPA — design system, routing, stores (Zustand 5.0), MSW, testing |

Deeper frontend subdocs: `docs/frontend/`

---

## Plans and Roadmaps

| Document | Description |
|----------|-------------|
| [`plans/AI_AGENT_ROADMAP.md`](plans/AI_AGENT_ROADMAP.md) | AI chat agent roadmap — structured data responses, rich results, streaming, history |

Other in-progress plans: `docs/plans/`, `docs/superpowers/plans/`

---

## Deeper Dives (`docs/backend/`)

The `docs/backend/` subtree contains longer tutorial-style documents that complement the reference docs above. They were written as part of a documentation migration effort. Per `docs/architecture/BACKEND.md`: the root-level (now category-folder) docs remain authoritative for quick reference; the `backend/` docs are longer tutorials and can be consulted for additional depth.

| Subfolder | Contents |
|-----------|----------|
| `docs/backend/architecture/` | Layered architecture deep dive, request flows, service discovery, security |
| `docs/backend/integrations/` | Per-integration tutorials: Scryfall, MTGJson, MTGStock, eBay, Shopify |
| `docs/backend/operations/` | Logging strategy, deployment, performance |
| `docs/backend/testing/` | Integration test approaches |
| `docs/backend/data-layer/` | Data layer patterns |
| `docs/backend/background-jobs/` | Celery and background job patterns |
