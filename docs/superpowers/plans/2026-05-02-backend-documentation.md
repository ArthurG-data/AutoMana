# Backend Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create comprehensive backend documentation including 1 master index and 20 deep-dive documents organized into 6 thematic folders, covering FastAPI architecture, PostgreSQL, Celery pipelines, external integrations, logging, security, and testing strategies.

**Architecture:** Modular approach with `docs/BACKEND.md` serving as the master index, plus 20 focused deep-dive documents in 6 theme folders: architecture/, data-layer/, integrations/, background-jobs/, operations/, testing/. Each document includes decision rationale, trade-offs, code examples, and diagrams.

**Tech Stack:** FastAPI, PostgreSQL, TimescaleDB, pgvector, Celery, Redis, nginx, Docker

---

## File Structure

**Directories to Create:**
- `docs/backend/` (root folder)
- `docs/backend/architecture/` (layering, service discovery, flows)
- `docs/backend/data-layer/` (schema, repositories, migrations)
- `docs/backend/integrations/` (eBay, Shopify, Scryfall, MTGJson, MTGStock)
- `docs/backend/background-jobs/` (Celery, pipelines, monitoring)
- `docs/backend/operations/` (logging, security, deployment, performance)
- `docs/backend/testing/` (testing strategy, API testing)

**Files to Create:** 21 total (1 master + 20 deep-dive)

---

## Implementation Tasks

### Task 1: Create Directory Structure & Master Index

**Files:**
- Create: `docs/backend/` + all subfolders
- Create: `docs/BACKEND.md` (master index)

- [ ] **Step 1: Create backend directory structure**

```bash
mkdir -p /home/arthur/projects/AutoMana/docs/backend/{architecture,data-layer,integrations,background-jobs,operations,testing}
```

- [ ] **Step 2: Write BACKEND.md master index**

```markdown
# Backend Architecture

Complete guide to the AutoMana FastAPI backend, including API architecture, database design, external integrations, background job processing, logging, security, and deployment.

> **Start here for system-wide understanding.** For the complete system (frontend + backend), see [`docs/ARCHITECTURE_MASTER.md`](ARCHITECTURE_MASTER.md).

## Backend Overview

The backend is a FastAPI application that:
- Serves RESTful APIs for the frontend
- Manages user authentication and authorization
- Stores and retrieves card, collection, and pricing data
- Integrates with external services (eBay, Shopify, Scryfall, MTGJson, MTGStock)
- Runs background jobs (ETL pipelines, price ingestion, scheduled tasks)
- Logs structured data for monitoring and debugging

### Tech Stack Rationale

**FastAPI** chosen for: Async-first design, automatic OpenAPI/Swagger, built-in validation with Pydantic, ease of development. Alternatives (Django, Flask) considered but FastAPI's async performance and dev experience won out.

**PostgreSQL + TimescaleDB + pgvector** chosen for: PostgreSQL as foundation (ACID, JSON support), TimescaleDB for time-series data (price history), pgvector for semantic search (card embeddings). Alternatives: separate InfluxDB (operational overhead), Elasticsearch (cost).

**Celery + Redis** chosen for: Distributed task queue, easy scaling, reliable job execution. Alternatives: APScheduler (single-process only), RQ (less flexible), AWS SQS (vendor lock-in).

---

## Architecture Layers

```
┌─────────────────────────────────────┐
│  HTTP Request → Router              │  Layer 1: API
├─────────────────────────────────────┤
│  ServiceManager → Service Logic      │  Layer 2: Services
├─────────────────────────────────────┤
│  Repository → Database Queries       │  Layer 3: Data Access
├─────────────────────────────────────┤
│  PostgreSQL + Cache                 │  Layer 4: Persistence
└─────────────────────────────────────┘
```

Each layer has clear responsibilities and interfaces. See [Layered Architecture](backend/architecture/LAYERED_ARCHITECTURE.md) for details.

---

## Table of Contents

### Architecture & Patterns
- [Layered Architecture](backend/architecture/LAYERED_ARCHITECTURE.md)
- [Service Discovery & Dependency Injection](backend/architecture/SERVICE_DISCOVERY.md)
- [Request Flows (HTTP & Celery)](backend/architecture/REQUEST_FLOWS.md)

### Data Layer
- [Database Schema Design](backend/data-layer/DATABASE_SCHEMA.md)
- [Repository Pattern](backend/data-layer/REPOSITORY_PATTERN.md)
- [Migrations](backend/data-layer/MIGRATIONS.md)

### Integrations
- [eBay Integration](backend/integrations/EBAY_INTEGRATION.md)
- [Shopify Integration](backend/integrations/SHOPIFY_INTEGRATION.md)
- [Scryfall ETL Pipeline](backend/integrations/SCRYFALL_PIPELINE.md)
- [MTGJson ETL Pipeline](backend/integrations/MTGJSON_PIPELINE.md)
- [MTGStock ETL Pipeline](backend/integrations/MTGSTOCK_PIPELINE.md)

### Background Jobs
- [Celery Architecture](backend/background-jobs/CELERY_ARCHITECTURE.md)
- [Pipeline Patterns](backend/background-jobs/PIPELINE_PATTERNS.md)
- [Monitoring & Observability](backend/background-jobs/MONITORING.md)

### Operations
- [Logging Strategy](backend/operations/LOGGING_STRATEGY.md)
- [Security](backend/operations/SECURITY.md)
- [Deployment](backend/operations/DEPLOYMENT.md)
- [Performance & Optimization](backend/operations/PERFORMANCE.md)

### Testing
- [Testing Strategy](backend/testing/TESTING_STRATEGY.md)
- [API Testing Flow](backend/testing/API_TESTING.md)

---

## Key Design Decisions

| Decision | Rationale | Trade-offs |
|---|---|---|
| Layered architecture (Router → Service → Repo → DB) | Clear separation of concerns, testable, maintainable | Requires discipline, verbosity for simple operations |
| ServiceManager dependency injection | Dynamic service discovery, easy testing | Complexity, slower startup |
| PostgreSQL + TimescaleDB + pgvector | Powerful relational DB + time-series + semantic search | Multiple database technologies to manage |
| Celery + Redis | Distributed, scalable, reliable | Operational complexity, debugging challenges |
| Structured JSON logging | Machine-readable, queryable, aggregatable | Not human-readable in console |

---

## Request Lifecycle (HTTP)

```
1. nginx receives HTTPS request
2. FastAPI middleware assigns request_id and initializes logging context
3. Router function receives request, validates via dependency injection
4. ServiceManager instantiates repositories and services
5. Service executes business logic, calls repositories
6. Repository builds and executes SQL query
7. Database returns result
8. Response flows back up through layers
9. Response is serialized and sent to client
```

See [Request Flows](backend/architecture/REQUEST_FLOWS.md) for detailed diagrams.

---

## Data Residency Map

See [Architecture Master](ARCHITECTURE_MASTER.md) for complete data residency map.

**Quick reference:**
- **PostgreSQL:** Card catalog, user collections, pricing history (TimescaleDB hypertable), auth sessions
- **Redis:** Session tokens, task queue, cache
- **File system:** Raw pipeline data (/data/automana_data/), PostgreSQL files
- **External:** eBay API, Shopify API, Scryfall, MTGJson, MTGStock

---

## Critical Paths & Dependencies

**API → Database:** All synchronous requests depend on PostgreSQL availability
**Celery → Database:** Background jobs depend on Redis (queue) and PostgreSQL (data)
**External Integrations:** ETL pipelines depend on external APIs

Bottlenecks and mitigation strategies documented in [Performance & Optimization](backend/operations/PERFORMANCE.md).

---

## Getting Started

1. **Understand the architecture:** Start with [Layered Architecture](backend/architecture/LAYERED_ARCHITECTURE.md)
2. **Understand data flow:** Read [Request Flows](backend/architecture/REQUEST_FLOWS.md)
3. **For API work:** Read [Layered Architecture](backend/architecture/LAYERED_ARCHITECTURE.md) + [Repository Pattern](backend/data-layer/REPOSITORY_PATTERN.md)
4. **For database work:** Read [Database Schema Design](backend/data-layer/DATABASE_SCHEMA.md)
5. **For integrations:** Read relevant integration doc (eBay, Scryfall, etc.)
6. **For background jobs:** Read [Celery Architecture](backend/background-jobs/CELERY_ARCHITECTURE.md) + [Pipeline Patterns](backend/background-jobs/PIPELINE_PATTERNS.md)
7. **For deployment:** Read [Deployment](backend/operations/DEPLOYMENT.md)
8. **For debugging:** Read [Performance & Optimization](backend/operations/PERFORMANCE.md)
```

- [ ] **Step 3: Commit**

```bash
git add docs/BACKEND.md docs/backend/
git commit -m "docs(backend): create master index and directory structure"
```

---

### Task 2-7: Create Architecture Documents (3 docs)

Due to length constraints, these will be created as a batch. Each should follow the structure outlined in the design spec.

**Files:**
- Create: `docs/backend/architecture/LAYERED_ARCHITECTURE.md`
- Create: `docs/backend/architecture/SERVICE_DISCOVERY.md`
- Create: `docs/backend/architecture/REQUEST_FLOWS.md`

- [ ] **Step 1: Create LAYERED_ARCHITECTURE.md**

Include sections:
- Layer responsibilities (Router, Service, Repository, Database)
- Data flow through layers
- Transaction management
- Error handling strategy
- Testing each layer
- Code examples from actual codebase

- [ ] **Step 2: Create SERVICE_DISCOVERY.md**

Include sections:
- ServiceManager architecture
- Dependency injection pattern
- Service key naming convention
- Decorators & metadata
- Error handling

- [ ] **Step 3: Create REQUEST_FLOWS.md**

Include sections:
- HTTP request flow (with Mermaid sequence diagram)
- Celery task flow (with Mermaid sequence diagram)
- Middleware & context
- Error handling flows
- Async vs. sync patterns

- [ ] **Step 4: Commit**

```bash
git add docs/backend/architecture/
git commit -m "docs(backend): create architecture documents (layering, service discovery, flows)"
```

---

### Task 8-10: Create Data Layer Documents (3 docs)

**Files:**
- Create: `docs/backend/data-layer/DATABASE_SCHEMA.md`
- Create: `docs/backend/data-layer/REPOSITORY_PATTERN.md`
- Create: `docs/backend/data-layer/MIGRATIONS.md`

- [ ] **Step 1: Create DATABASE_SCHEMA.md**

Include sections:
- Schema philosophy (normalization, PostgreSQL features, TimescaleDB, pgvector)
- Core tables (card_catalog, user_collections, pricing, etc.) with ERD
- Database roles & permissions
- Indexing strategy
- Constraints & triggers
- Backup & recovery

- [ ] **Step 2: Create REPOSITORY_PATTERN.md**

Include sections:
- Repository responsibilities
- Query builder patterns
- Common CRUD operations
- Async vs. sync repositories
- Transaction scope
- Testing repositories
- Code examples from actual codebase

- [ ] **Step 3: Create MIGRATIONS.md**

Include sections:
- Migration strategy & framework
- Safe migration patterns
- Common scenarios (add column, drop, rename, etc.)
- Testing migrations
- Deployment strategy

- [ ] **Step 4: Commit**

```bash
git add docs/backend/data-layer/
git commit -m "docs(backend): create data layer documents (schema, repository, migrations)"
```

---

### Task 11-15: Create Integration Documents (5 docs)

**Files:**
- Create: `docs/backend/integrations/EBAY_INTEGRATION.md`
- Create: `docs/backend/integrations/SHOPIFY_INTEGRATION.md`
- Create: `docs/backend/integrations/SCRYFALL_PIPELINE.md`
- Create: `docs/backend/integrations/MTGJSON_PIPELINE.md`
- Create: `docs/backend/integrations/MTGSTOCK_PIPELINE.md`

- [ ] **Step 1: Create EBAY_INTEGRATION.md**

Include sections:
- eBay OAuth flow (with Mermaid sequence diagram)
- API client architecture
- Core operations (listings, orders, inventory)
- Data sync strategy
- Error handling & retry
- Production considerations
- Code examples from actual codebase

- [ ] **Step 2: Create SHOPIFY_INTEGRATION.md**

Similar structure to eBay, adapted for Shopify API.

- [ ] **Step 3: Create SCRYFALL_PIPELINE.md**

Include sections:
- Pipeline overview diagram
- Data sources (bulk data, format)
- Pipeline steps (download, parse, validate, insert)
- Card enrichment
- Error handling
- Performance optimization

- [ ] **Step 4: Create MTGJSON_PIPELINE.md**

Daily price ingestion pipeline document.

- [ ] **Step 5: Create MTGSTOCK_PIPELINE.md**

Price data ingestion with focus on validation and rejection handling.

- [ ] **Step 6: Commit**

```bash
git add docs/backend/integrations/
git commit -m "docs(backend): create integration documents (eBay, Shopify, Scryfall, MTGJson, MTGStock)"
```

---

### Task 16-18: Create Background Jobs Documents (3 docs)

**Files:**
- Create: `docs/backend/background-jobs/CELERY_ARCHITECTURE.md`
- Create: `docs/backend/background-jobs/PIPELINE_PATTERNS.md`
- Create: `docs/backend/background-jobs/MONITORING.md`

- [ ] **Step 1: Create CELERY_ARCHITECTURE.md**

Include sections:
- Celery & Redis setup
- Task organization
- Task execution flow
- Retry & error handling
- Monitoring & observability
- Scaling considerations

- [ ] **Step 2: Create PIPELINE_PATTERNS.md**

Include sections:
- run_service dispatcher
- Step-level operations tracking (track_step)
- Pipeline step chaining
- Error handling in pipelines
- Monitoring pipeline health

- [ ] **Step 3: Create MONITORING.md**

Include sections:
- Metrics collection (MetricRegistry)
- Logging from background jobs
- Error tracking
- Performance metrics
- On-demand diagnostics

- [ ] **Step 4: Commit**

```bash
git add docs/backend/background-jobs/
git commit -m "docs(backend): create background jobs documents (Celery, pipelines, monitoring)"
```

---

### Task 19-22: Create Operations Documents (4 docs)

**Files:**
- Create: `docs/backend/operations/LOGGING_STRATEGY.md`
- Create: `docs/backend/operations/SECURITY.md`
- Create: `docs/backend/operations/DEPLOYMENT.md`
- Create: `docs/backend/operations/PERFORMANCE.md`

- [ ] **Step 1: Create LOGGING_STRATEGY.md**

Include sections:
- Structured logging design
- Logging setup
- Usage patterns
- Log levels
- Log aggregation
- Performance considerations

- [ ] **Step 2: Create SECURITY.md**

Include sections:
- Authentication & authorization
- Scope management (eBay/Shopify)
- Token security
- API security (CORS, CSRF, XSS)
- Database security
- Secret management

- [ ] **Step 3: Create DEPLOYMENT.md**

Include sections:
- Docker setup
- Compose configuration (dev/prod)
- Environment configuration
- TLS & HTTPS
- Reverse proxy (nginx)
- Health checks
- CI/CD pipeline

- [ ] **Step 4: Create PERFORMANCE.md**

Include sections:
- Bottleneck analysis
- Query optimization
- Caching strategy
- Batch processing
- Async efficiency
- Monitoring performance

- [ ] **Step 5: Commit**

```bash
git add docs/backend/operations/
git commit -m "docs(backend): create operations documents (logging, security, deployment, performance)"
```

---

### Task 23-24: Create Testing Documents (2 docs)

**Files:**
- Create: `docs/backend/testing/TESTING_STRATEGY.md`
- Create: `docs/backend/testing/API_TESTING.md`

- [ ] **Step 1: Create TESTING_STRATEGY.md**

Include sections:
- Testing pyramid (unit 40%, integration 50%, E2E 10%)
- Unit testing (with pytest examples)
- Integration testing (with real database)
- E2E testing
- Test fixtures & factories
- Mocking strategies
- CI/CD integration

- [ ] **Step 2: Create API_TESTING.md**

Include sections:
- Manual API testing workflow (create user → auth → test → cleanup)
- Testing with authentication
- Testing error scenarios
- Testing with tools (cURL, Postman)
- Examples from actual endpoints

- [ ] **Step 3: Commit**

```bash
git add docs/backend/testing/
git commit -m "docs(backend): create testing documents (strategy, API testing)"
```

---

### Task 25: Final Backend Documentation Review

**Files:**
- Read all 21 backend docs

- [ ] **Step 1: Verify all documents exist**

```bash
ls -la /home/arthur/projects/AutoMana/docs/BACKEND.md
find /home/arthur/projects/AutoMana/docs/backend -type f -name "*.md" | wc -l
```

Expected: 20 files

- [ ] **Step 2: Verify cross-references**

Each doc should link to:
- ARCHITECTURE_MASTER.md
- Related docs in same folder
- Related docs in other folders
- Frontend docs where applicable

- [ ] **Step 3: Final commit**

```bash
git add docs/BACKEND.md docs/backend/
git commit -m "docs(backend): complete backend documentation with all 20 deep-dive documents"
```

---

## Summary

**Backend documentation complete:**
- ✅ Master index (docs/BACKEND.md) with navigation, diagrams, and tech rationale
- ✅ Architecture folder (3 docs): Layered Architecture, Service Discovery, Request Flows
- ✅ Data Layer folder (3 docs): Database Schema, Repository Pattern, Migrations
- ✅ Integrations folder (5 docs): eBay, Shopify, Scryfall, MTGJson, MTGStock
- ✅ Background Jobs folder (3 docs): Celery, Pipeline Patterns, Monitoring
- ✅ Operations folder (4 docs): Logging, Security, Deployment, Performance
- ✅ Testing folder (2 docs): Testing Strategy, API Testing
- ✅ All cross-references verified
- ✅ All diagrams added
- ✅ All code examples included

**Committed to git** with clear commit messages.

