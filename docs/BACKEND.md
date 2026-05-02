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

**FastAPI** chosen for:
- Async-first design enabling high concurrency
- Automatic OpenAPI/Swagger documentation
- Built-in validation with Pydantic models
- Development velocity and ease of testing
- Strong type hints support

Alternatives (Django, Flask) were considered but FastAPI's async performance, developer experience, and modern Python ecosystem integration made it the clear choice.

**PostgreSQL + TimescaleDB + pgvector** chosen for:
- **PostgreSQL:** Foundation database (ACID compliance, JSON support, row-level security)
- **TimescaleDB:** Purpose-built extension for time-series data (price history, card price movements)
- **pgvector:** Vector database extension for semantic search capabilities (card embeddings, similarity matching)

Alternatives: Separate InfluxDB would increase operational overhead; Elasticsearch would add licensing costs; document-only stores (MongoDB) lack the relational structure needed for collections and user data.

**Celery + Redis** chosen for:
- Distributed task queue supporting horizontal scaling
- Reliable job execution with retry mechanisms
- Background ETL pipeline execution without blocking HTTP requests
- Task scheduling (e.g., daily price updates)

Alternatives: APScheduler (single-process only), RQ (less flexible scheduling), AWS SQS (vendor lock-in), direct async tasks (insufficient for distributed work).

## Architecture Layers

```
┌─────────────────────────────────────────────┐
│         HTTP Clients / Frontend              │
└─────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│  Router Layer (FastAPI Endpoints)            │
│  - Request validation (Pydantic)             │
│  - HTTP semantics (GET, POST, etc)          │
│  - Response serialization                    │
└─────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│  Service Layer (Business Logic)              │
│  - ServiceManager dependency injection       │
│  - Orchestration of repositories            │
│  - Transaction management                    │
│  - Domain logic                              │
└─────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│  Repository Layer (Data Abstraction)         │
│  - SQL query construction                    │
│  - ORM/query builder usage                   │
│  - Result mapping                            │
└─────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│  Database Layer (PostgreSQL)                 │
│  - Relational data storage                   │
│  - TimescaleDB for time-series               │
│  - pgvector for semantic search              │
└─────────────────────────────────────────────┘

Background Jobs Path:
┌─────────────────────────────────────────────┐
│  Celery Worker Tasks (task_id)               │
│  - ETL pipeline jobs                         │
│  - Scheduled tasks (daily, hourly)          │
└─────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│  Service Layer (Reused from HTTP layer)      │
└─────────────────────────────────────────────┘
```

Each layer has clear responsibilities and interfaces. No layer skips steps; data always flows through the complete stack.

## Table of Contents

### Architecture & Patterns
- [Layered Architecture](backend/architecture/LAYERED_ARCHITECTURE.md) — Detailed responsibility breakdown, module organization, and layer interfaces
- [Service Discovery & Dependency Injection](backend/architecture/SERVICE_DISCOVERY.md) — ServiceManager implementation, provider patterns, testing with mocks
- [Request Flows (HTTP & Celery)](backend/architecture/REQUEST_FLOWS.md) — End-to-end HTTP request lifecycle, Celery task execution flow, error handling

### Data Layer
- [Database Schema Design](backend/data-layer/DATABASE_SCHEMA.md) — Core tables (users, collections, cards, pricing), relationships, constraints, and design rationale
- [Repository Pattern](backend/data-layer/REPOSITORY_PATTERN.md) — Query builders, result mapping, repository interface contracts, testing patterns
- [Migrations & Schema Evolution](backend/data-layer/MIGRATIONS.md) — Migration file structure, schema versioning, deploying changes safely, rollback procedures

### Integrations
- [eBay Integration](backend/integrations/EBAY_INTEGRATION.md) — API authentication, inventory sync, pricing updates, error handling
- [Shopify Integration](backend/integrations/SHOPIFY_INTEGRATION.md) — Webhook handling, fulfillment tracking, product data sync
- [Scryfall ETL Pipeline](backend/integrations/SCRYFALL_PIPELINE.md) — Card data ingestion, bulk data loading, incremental updates, data validation
- [MTGJson ETL Pipeline](backend/integrations/MTGJSON_PIPELINE.md) — Comprehensive card metadata, set information, price linking, processing strategy
- [MTGStock ETL Pipeline](backend/integrations/MTGSTOCK_PIPELINE.md) — Price observation ingestion, historical tracking, rate limiting, batching

### Background Jobs & Pipelines
- [Celery Architecture](backend/background-jobs/CELERY_ARCHITECTURE.md) — Task definitions, worker configuration, queue management, task state tracking
- [Pipeline Patterns & Conventions](backend/background-jobs/PIPELINE_PATTERNS.md) — Step-based pipeline pattern, context passing, error recovery, ops tracking
- [Monitoring & Observability](backend/background-jobs/MONITORING.md) — Task monitoring, pipeline observability, alerts, metrics collection

### Operations
- [Logging Strategy](backend/operations/LOGGING_STRATEGY.md) — Structured JSON logging, context propagation, log levels, field conventions
- [Security](backend/operations/SECURITY.md) — Authentication, authorization, JWT tokens, secrets management, database roles
- [Deployment](backend/operations/DEPLOYMENT.md) — Docker setup, environment configuration, startup sequences, health checks
- [Performance & Optimization](backend/operations/PERFORMANCE.md) — Query optimization, caching strategy, bottleneck identification, profiling tools

### Testing
- [Testing Strategy](backend/testing/TESTING_STRATEGY.md) — Unit tests, integration tests, fixtures, mocking strategies, test data
- [API Testing Flow](backend/testing/API_TESTING.md) — Manual API testing workflow, user creation, authentication, cleanup procedures

## Key Design Decisions

| Decision | Rationale | Trade-offs |
|----------|-----------|-----------|
| Strict layered architecture (Router → Service → Repo → DB) | Clear separation of concerns, independently testable layers, enforced by code structure | Requires discipline to not bypass layers, verbosity for simple CRUD operations |
| ServiceManager dependency injection | Dynamic service instantiation, easy to mock for testing, centralized provider management | Adds complexity at startup, slight performance cost for provider lookups |
| PostgreSQL + TimescaleDB + pgvector | Single PostgreSQL connection string, time-series support without separate systems, semantic search without external service | Multiple PostgreSQL extensions to manage, feature parity depends on PG version |
| Celery + Redis | Proven distributed task queue, horizontal scaling, retries and error handling built-in | Operational complexity, distributed debugging challenges, requires Redis availability |
| Structured JSON logging | Machine-readable, easily aggregatable into observability platforms, queryable in logs | Not human-readable in console, requires log aggregation setup for full value |
| Service-first architecture over repositories | Services encapsulate business logic and coordinate operations, repositories remain simple | Services can become "god objects" if not carefully designed, requires clear boundaries |
| Async throughout (FastAPI + asyncpg) | High concurrency, efficient I/O, non-blocking behavior | Python async ecosystem less mature than sync, asyncpg pool management complexity |

## Request Lifecycle (HTTP)

1. **HTTPS received by nginx** — TLS termination, routing to backend
2. **FastAPI middleware chain** — Request ID assignment, logging context initialization
3. **Router function receives request** — Dependency injection resolves auth, services, etc.
4. **ServiceManager instantiation** — Repositories and services created with injected dependencies
5. **Service executes business logic** — Validation, orchestration, calling repositories
6. **Repository builds SQL query** — Query builder constructs parameterized query, applies filters
7. **Database query execution** — asyncpg sends query, PostgreSQL executes, returns results
8. **Result mapping** — Repository maps rows to domain objects
9. **Business logic continues** — Service may invoke multiple repositories, apply transformations
10. **Response construction** — Router serializes response via Pydantic model
11. **HTTP response sent** — FastAPI serializes to JSON, sets headers, sends to client
12. **Middleware finalization** — Logging context dumped to JSON, request metrics recorded

## Data Residency Map

| Component | Storage | Purpose | Durability |
|-----------|---------|---------|-----------|
| Card catalog | PostgreSQL | Master card data (name, rules, images) | ACID, replicated |
| User collections | PostgreSQL | User's cards and ownership records | ACID, replicated |
| Pricing history | TimescaleDB hypertable | Price observations over time, analytics | ACID, optimized for time-series queries |
| User sessions | Redis + PostgreSQL | Active sessions, JWT tokens | In-memory with disk backup |
| Task queue | Redis | Celery job queue and task state | Volatile, lossy acceptable for retryable jobs |
| Cache | Redis | Computed results, external API responses | Volatile, non-critical |
| Raw pipeline data | File system (/data/automana_data/) | Downloaded dumps (Scryfall, MTGJson, MTGStock) | Durable, for audit trail |
| External services | eBay, Shopify, Scryfall, MTGJson, MTGStock | Authoritative sources for pricing and data | External, accessed via API |

## Getting Started

**For API Development:**
1. Read [Layered Architecture](backend/architecture/LAYERED_ARCHITECTURE.md) to understand module organization
2. Read [Request Flows](backend/architecture/REQUEST_FLOWS.md) for HTTP request handling
3. Review [Repository Pattern](backend/data-layer/REPOSITORY_PATTERN.md) for data access

**For Database Work:**
1. Start with [Database Schema Design](backend/data-layer/DATABASE_SCHEMA.md)
2. Read [Migrations & Schema Evolution](backend/data-layer/MIGRATIONS.md) before making schema changes
3. Reference [Performance & Optimization](backend/operations/PERFORMANCE.md) for query optimization

**For Integration Work:**
1. Read the specific integration document (eBay, Shopify, Scryfall, MTGJson, MTGStock)
2. Review [Request Flows](backend/architecture/REQUEST_FLOWS.md) for how integrations fit into the system

**For Background Jobs:**
1. Read [Celery Architecture](backend/background-jobs/CELERY_ARCHITECTURE.md) for task setup
2. Read [Pipeline Patterns & Conventions](backend/background-jobs/PIPELINE_PATTERNS.md) for ETL work
3. Reference [Monitoring & Observability](backend/background-jobs/MONITORING.md) for task tracking

**For Deployment:**
1. Read [Deployment](backend/operations/DEPLOYMENT.md)
2. Reference [Security](backend/operations/SECURITY.md) for secrets and authentication setup

**For Debugging:**
1. Start with [Logging Strategy](backend/operations/LOGGING_STRATEGY.md)
2. Read [Performance & Optimization](backend/operations/PERFORMANCE.md)
3. Reference [Testing Strategy](backend/testing/TESTING_STRATEGY.md) for reproduction techniques

**For Testing:**
1. Read [Testing Strategy](backend/testing/TESTING_STRATEGY.md) for test organization and fixtures
2. Use [API Testing Flow](backend/testing/API_TESTING.md) for manual testing procedures

## Architecture Decision Records

This documentation captures the current state of the backend. Major architectural decisions are documented in the respective sections above. For detailed rationale on specific patterns, see [DESIGN_PATTERNS.md](DESIGN_PATTERNS.md).

## Cross-References

- **Full system architecture:** See [`docs/ARCHITECTURE_MASTER.md`](ARCHITECTURE_MASTER.md)
- **Frontend architecture:** See [`docs/FRONTEND.md`](FRONTEND.md)
- **API endpoints reference:** See [`docs/API.md`](API.md)
- **Design patterns lexicon:** See [`docs/DESIGN_PATTERNS.md`](DESIGN_PATTERNS.md)
