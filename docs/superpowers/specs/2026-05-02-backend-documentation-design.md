---
title: Comprehensive Backend Documentation Design
date: 2026-05-02
status: approved
---

# Comprehensive Backend Documentation Design

## Goal

Create a complete, in-depth backend knowledge base that serves two purposes:
1. **Reference guide for deep technical knowledge** — understand every component of the FastAPI backend, how they work, and why design choices were made
2. **Architecture analysis document** — structured explanation of design choices, trade-offs considered, and how components interact

## Approach: Modular Deep-Dive Architecture

A **master index document** (`docs/BACKEND.md`) that ties everything together, plus **focused deep-dive documents** for major subsystems, with **selective enhancements** to existing docs where needed.

## Document Structure

### Folder Organization

Documents organized by theme in subfolders under `docs/backend/`:

```
docs/
├── BACKEND.md                           (master index)
└── backend/
    ├── architecture/                    (core architecture & patterns)
    │   ├── LAYERED_ARCHITECTURE.md     (router → service → repository → database layering)
    │   ├── SERVICE_DISCOVERY.md        (ServiceManager, service registration, dependency injection)
    │   └── REQUEST_FLOWS.md            (HTTP request flow, Celery task flow, error handling)
    │
    ├── data-layer/                      (database & data access)
    │   ├── DATABASE_SCHEMA.md          (PostgreSQL schema, TimescaleDB, pgvector design)
    │   ├── REPOSITORY_PATTERN.md       (repository layer, query building, transaction management)
    │   └── MIGRATIONS.md               (schema migrations, deployment strategy)
    │
    ├── integrations/                    (external integrations)
    │   ├── EBAY_INTEGRATION.md         (eBay OAuth, API calls, data sync)
    │   ├── SHOPIFY_INTEGRATION.md      (Shopify API integration)
    │   ├── SCRYFALL_PIPELINE.md        (Scryfall ETL, card data ingestion)
    │   ├── MTGJSON_PIPELINE.md         (MTGJson daily price ingestion)
    │   └── MTGSTOCK_PIPELINE.md        (MTGStocks price pipeline, data validation)
    │
    ├── background-jobs/                 (async processing)
    │   ├── CELERY_ARCHITECTURE.md      (Celery setup, task organization, retry logic)
    │   ├── PIPELINE_PATTERNS.md        (run_service dispatcher, step tracking, state management)
    │   └── MONITORING.md               (task monitoring, error tracking, metrics)
    │
    ├── operations/                      (logging, security, deployment)
    │   ├── LOGGING_STRATEGY.md         (structured logging, context vars, JSON output)
    │   ├── SECURITY.md                 (authentication, authorization, scopes, XSS/CSRF prevention)
    │   ├── DEPLOYMENT.md               (Docker, nginx, environment config, TLS)
    │   └── PERFORMANCE.md              (bottlenecks, scaling strategy, optimization)
    │
    └── testing/                         (testing approach)
        ├── TESTING_STRATEGY.md         (unit, integration, E2E; fixtures; mocking)
        └── API_TESTING.md              (manual API testing flow, auth testing)
```

### Master Index Document: `docs/BACKEND.md`

**Purpose:** Entry point for understanding the backend architecture, how pieces fit together, and key design decisions.

**Sections:**

1. **Backend Overview** (300-500 words)
   - What the FastAPI backend does, core responsibilities
   - Tech stack rationale (FastAPI, PostgreSQL + TimescaleDB + pgvector, Celery, Redis, nginx)
   - Current state and maintenance

2. **Architecture Diagram** (Mermaid)
   - Visual map of: API → ServiceManager → Services → Repositories → Database
   - Background jobs flow: Celery → Services → Database

3. **Request Lifecycle** (Mermaid sequence diagram)
   - HTTP: request → middleware → router → service → repository → database → response
   - Celery: trigger → task queue → worker → service → repository → database

4. **Production vs. Dev Topology** (ASCII/Mermaid diagrams)
   - Production: nginx → FastAPI → {Postgres, Redis} (with TLS, secrets management)
   - Dev: nginx → ngrok tunnel → FastAPI → {Postgres, Redis, Celery}

5. **Layered Architecture Overview** (Mermaid diagram)
   - Router layer, ServiceManager, Services, Repositories, Database
   - Data flow and responsibility boundaries

6. **Table of Contents & Navigation**
   - Links to all 10+ deep-dive documents with 1-line summary
   - Links to related frontend docs (API surface, auth)

7. **Key Design Decisions Summary** (table)
   - Major decision → rationale → trade-offs → link to detailed discussion
   - Examples:
     - Why FastAPI over Django/Flask?
     - Why layered architecture (router → service → repo)?
     - Why Celery + Redis for background jobs?
     - Why PostgreSQL + TimescaleDB + pgvector?
     - Why ServiceManager dependency injection pattern?
     - Why structured JSON logging?

8. **Operational Considerations**
   - Scaling bottlenecks and mitigation
   - Resource requirements and tuning
   - Monitoring and alerting strategy

---

## Deep-Dive Documents

### Architecture Theme

#### **Document 1: Layered Architecture**
**File:** `docs/backend/architecture/LAYERED_ARCHITECTURE.md`

**Content:**

1. **Layer Responsibilities** (800 words)
   - Router layer: HTTP parsing, auth, dependency injection
   - Service layer: business logic, transactions, error handling
   - Repository layer: database queries, entity mapping
   - Database layer: schema, constraints, indexing
   - Why this layering? Trade-offs vs. alternatives?

2. **Data Flow Through Layers**
   - Request enters at router
   - ServiceManager instantiates repositories and services
   - Service calls repositories
   - Repositories use AsyncQueryExecutor
   - Response flows back up

3. **Transaction Management**
   - Transaction scope (per service call)
   - Rollback on error
   - Serialization strategy

4. **Error Handling Strategy**
   - Exception hierarchy
   - Which layer catches what
   - Error propagation and transformation

5. **Testing Each Layer**
   - Router unit tests (mock services)
   - Service integration tests (real repositories)
   - Repository tests (real database)

---

#### **Document 2: Service Discovery & Dependency Injection**
**File:** `docs/backend/architecture/SERVICE_DISCOVERY.md`

**Content:**

1. **ServiceManager Architecture** (600 words)
   - Singleton pattern
   - Service registry and discovery
   - Dynamic module loading
   - Dependency resolution

2. **Dependency Injection Pattern**
   - How services and repositories are instantiated
   - Automatic parameter resolution by type hints
   - Order of instantiation

3. **Service Key Naming Convention**
   - Hierarchical naming (e.g., `scryfall.ingest.cards`)
   - Discovery from file system structure

4. **Decorators & Metadata**
   - How services are registered
   - Service path mapping

5. **Error Handling**
   - Service not found errors
   - Circular dependency detection
   - Missing parameter errors

---

#### **Document 3: Request Flows**
**File:** `docs/backend/architecture/REQUEST_FLOWS.md`

**Content:**

1. **HTTP Request Flow** (Mermaid sequence diagram + description)
   - Client → nginx → FastAPI middleware → router function → ServiceManager.execute_service → service logic → repository queries → response

2. **Celery Task Flow** (Mermaid sequence diagram)
   - Trigger (beat scheduler or external) → task queue → worker picks up → run_service dispatcher → service logic → database updates

3. **Middleware & Context**
   - Request ID assignment
   - Logging context setup
   - Auth middleware

4. **Error Handling Flows**
   - API error responses
   - Celery task error handling and retry

5. **Async vs. Sync Patterns**
   - Async path: asyncpg, AsyncQueryExecutor
   - Sync path: psycopg2, for certain operations
   - When to use each

---

### Data Layer Theme

#### **Document 4: Database Schema Design**
**File:** `docs/backend/data-layer/DATABASE_SCHEMA.md`

**Content:**

1. **Schema Philosophy** (700 words)
   - PostgreSQL feature usage (enums, arrays, JSONB, constraints)
   - TimescaleDB for price history (hypertable design)
   - pgvector for card embeddings/similarity search
   - Normalization strategy
   - Why these choices? Alternatives considered?

2. **Core Tables**
   - `card_catalog` — normalized card definitions
   - `user_collections` — user's cards
   - `pricing.price_observations` — TimescaleDB hypertable
   - `card_embeddings` — pgvector storage
   - Entity relationship diagram (ERD)

3. **Database Roles & Permissions**
   - `admin_db`, `app_api`, `app_celery`, `analytics`
   - Permission model per role
   - Secret management for credentials

4. **Indexing Strategy**
   - Indexes on foreign keys
   - Composite indexes for common queries
   - Performance implications

5. **Constraints & Triggers**
   - Primary keys, foreign keys, unique constraints
   - Check constraints for data validation
   - Triggers for denormalization or auditing

6. **Backup & Recovery**
   - Backup strategy
   - Point-in-time recovery
   - Testing backups

---

#### **Document 5: Repository Pattern**
**File:** `docs/backend/data-layer/REPOSITORY_PATTERN.md`

**Content:**

1. **Repository Responsibilities** (600 words)
   - Query building and execution
   - Result mapping to domain objects
   - Transaction management
   - Error handling (constraint violations, not found, etc.)

2. **Query Builder Patterns**
   - SQL construction
   - Parameter binding (SQL injection prevention)
   - Dynamic query building for filters/pagination

3. **Common Repository Operations**
   - CRUD patterns
   - Bulk operations
   - Pagination and sorting
   - Filtering and search

4. **Async vs. Sync Repositories**
   - AsyncRepository with asyncpg
   - SyncRepository with psycopg2
   - When to use each

5. **Transaction Scope**
   - Transaction lifecycle
   - Rollback scenarios
   - Savepoints for nested operations

6. **Testing Repositories**
   - Real database fixtures
   - Transaction rollback between tests
   - Data seeding strategies

---

#### **Document 6: Migrations**
**File:** `docs/backend/data-layer/MIGRATIONS.md`

**Content:**

1. **Migration Strategy** (500 words)
   - Migration framework/tool used
   - Version numbering scheme
   - File organization and naming

2. **Safe Migration Patterns**
   - Backwards compatibility (can old code run against new schema?)
   - Zero-downtime migrations
   - Rollback safety

3. **Common Migration Scenarios**
   - Adding columns, dropping columns
   - Renaming tables/columns
   - Creating/modifying indexes
   - Data transformation migrations

4. **Testing Migrations**
   - Testing upgrades
   - Testing rollbacks
   - Large table migration testing

5. **Deployment Strategy**
   - When migrations run (before code deploy?)
   - Monitoring migration success
   - Rollback procedures

---

### Integrations Theme

#### **Document 7: eBay Integration**
**File:** `docs/backend/integrations/EBAY_INTEGRATION.md`

**Content:**

1. **eBay OAuth Flow** (Mermaid sequence diagram + explanation)
   - Authorization code flow
   - Token refresh mechanism
   - Scope encoding and storage
   - Why this approach? Alternatives?

2. **API Client Architecture**
   - HTTP client setup
   - Request signing
   - Error handling for eBay errors

3. **Core Operations**
   - Fetching listings
   - Getting order history
   - Updating inventory

4. **Data Sync Strategy**
   - Incremental vs. full sync
   - Conflict resolution
   - Deduplication

5. **Error Handling & Retry**
   - Rate limiting
   - Temporary vs. permanent errors
   - Exponential backoff strategy

6. **Production Considerations**
   - Scope requirements for production
   - Sandbox vs. production endpoints
   - Token expiration and refresh

---

#### **Document 8: Shopify Integration**
**File:** `docs/backend/integrations/SHOPIFY_INTEGRATION.md`

**Content:** (Similar structure to eBay, adapted for Shopify API)

---

#### **Document 9: Scryfall ETL Pipeline**
**File:** `docs/backend/integrations/SCRYFALL_PIPELINE.md`

**Content:**

1. **Pipeline Overview** (Mermaid diagram)
   - Scryfall bulk data download → parsing → database ingestion
   - Why this approach vs. API calls?

2. **Data Sources**
   - Bulk data endpoint
   - Data format (JSON)
   - Update frequency

3. **Pipeline Steps**
   - Download
   - Parse/transform
   - Validation
   - Deduplication
   - Insert/update database
   - Step-level ops tracking

4. **Card Enrichment**
   - Scryfall data structure
   - Mapping to card_catalog schema
   - Handling variants and reprints

5. **Error Handling**
   - Validation errors
   - Duplicate handling
   - Data quality checks

6. **Performance Optimization**
   - Batch insertion
   - Index disabling during bulk load
   - Parallel processing where applicable

---

#### **Document 10: MTGJson Pipeline**
**File:** `docs/backend/integrations/MTGJSON_PIPELINE.md`

**Content:** (Daily price ingestion; similar structure with focus on pricing)

---

#### **Document 11: MTGStock Pipeline**
**File:** `docs/backend/integrations/MTGSTOCK_PIPELINE.md`

**Content:** (Price data ingestion; data validation and rejection handling)

---

### Background Jobs Theme

#### **Document 12: Celery Architecture**
**File:** `docs/backend/background-jobs/CELERY_ARCHITECTURE.md`

**Content:**

1. **Celery & Redis Setup** (600 words)
   - Why Celery + Redis?
   - Broker configuration
   - Worker pool strategy (concurrency, prefetch)
   - Beat scheduler setup

2. **Task Organization**
   - Task modules and naming
   - Task routing
   - Task types (one-off vs. periodic)

3. **Task Execution Flow**
   - Task enqueue
   - Worker pickup
   - Execution context
   - Result storage

4. **Retry & Error Handling**
   - Retry strategies (exponential backoff)
   - Max retries
   - Dead letter queue handling
   - Error logging

5. **Monitoring & Observability**
   - Task status tracking
   - Success/failure metrics
   - Dead tasks and alerts

6. **Scaling Considerations**
   - Adding workers
   - Load balancing
   - Resource allocation

---

#### **Document 13: Pipeline Patterns**
**File:** `docs/backend/background-jobs/PIPELINE_PATTERNS.md`

**Content:**

1. **Run Service Dispatcher** (500 words)
   - How pipelines are executed
   - Service key routing
   - Parameter passing between steps
   - Context/state management

2. **Step-Level Operations Tracking**
   - `track_step` context manager
   - Ingestion runs table
   - Status transitions (running → success/failed)
   - Error details capture

3. **Pipeline Step Chaining**
   - Output of one step as input to next
   - Parameter name matching
   - Conditional step execution

4. **Error Handling in Pipelines**
   - Step-level errors
   - Partial success/rollback
   - Retry at step level

5. **Monitoring Pipeline Health**
   - Step completion times
   - Success rates
   - Data quality metrics

---

#### **Document 14: Monitoring & Observability**
**File:** `docs/backend/background-jobs/MONITORING.md`

**Content:**

1. **Metrics Collection** (600 words)
   - MetricRegistry decorator
   - Sanity report runner pattern
   - Health metrics (card_catalog, pricing)

2. **Logging from Background Jobs**
   - Structured logging in Celery tasks
   - Request context in async context
   - Log aggregation and search

3. **Error Tracking**
   - Task failure notifications
   - Error categorization
   - Alerting thresholds

4. **Performance Metrics**
   - Task execution time
   - Queue depth
   - Worker utilization

5. **On-Demand Diagnostics**
   - Scryfall audit tool
   - Data quality checks
   - Consistency verification

---

### Operations Theme

#### **Document 15: Logging Strategy**
**File:** `docs/backend/operations/LOGGING_STRATEGY.md`

**Content:**

1. **Structured Logging Design** (700 words)
   - JSON output format
   - Context variables (request_id, service_path, user_id)
   - Why structured over plain text?

2. **Logging Setup**
   - `configure_logging()` initialization
   - Handler configuration
   - Log level strategy

3. **Usage Patterns**
   - Correct logging idiom: static message + extra dict
   - Avoid interpolation into message strings
   - Context variable usage

4. **Log Levels**
   - When to use DEBUG, INFO, WARNING, ERROR, CRITICAL
   - Operational meaning of each level

5. **Log Aggregation**
   - Shipping logs to central system
   - Querying and filtering
   - Alert setup

6. **Performance Considerations**
   - Logging overhead
   - Sampling strategies
   - Async logging

---

#### **Document 16: Security**
**File:** `docs/backend/operations/SECURITY.md`

**Content:**

1. **Authentication & Authorization** (800 words)
   - Session cookie auth mechanism
   - Permission checking in services
   - Why this approach? Alternatives?

2. **Scope Management**
   - eBay/Shopify scope storage
   - Scope truncation for production
   - User scope validation

3. **Token Security**
   - Token storage (avoid secrets in code)
   - Token rotation strategies
   - Expiration handling

4. **API Security**
   - CORS configuration
   - CSRF protection
   - Input validation and sanitization
   - XSS prevention

5. **Database Security**
   - Role-based access (app_api vs. app_celery vs. admin)
   - Connection pooling security
   - Credential management

6. **Secret Management**
   - Environment variables
   - Docker secrets
   - Rotation procedures

---

#### **Document 17: Deployment**
**File:** `docs/backend/operations/DEPLOYMENT.md`

**Content:**

1. **Docker Setup** (800 words)
   - Dockerfile design
   - Multi-stage builds
   - Layer optimization
   - Why Docker?

2. **Compose Configuration**
   - Dev compose file
   - Prod compose file
   - Service dependencies
   - Volume management

3. **Environment Configuration**
   - .env files
   - Environment variable injection
   - Config per environment (dev/staging/prod)

4. **TLS & HTTPS**
   - Certificate management
   - Self-signed vs. real certificates
   - Renewal procedures

5. **Reverse Proxy (nginx)**
   - Configuration rationale
   - Port mapping
   - Request forwarding
   - Performance tuning

6. **Health Checks**
   - Lifespan setup
   - Health endpoint
   - Readiness checks for workers

7. **CI/CD Pipeline**
   - Build steps
   - Tests before deploy
   - Deployment checklist

---

#### **Document 18: Performance & Optimization**
**File:** `docs/backend/operations/PERFORMANCE.md`

**Content:**

1. **Bottleneck Analysis** (600 words)
   - Database query performance
   - Slow API endpoints
   - Pipeline execution time
   - Profiling strategies

2. **Query Optimization**
   - N+1 query problem
   - Batch queries
   - Eager loading of relationships
   - Index effectiveness

3. **Caching Strategy**
   - Redis usage
   - Cache invalidation
   - Cache misses and cold starts
   - Distributed caching

4. **Batch Processing**
   - Bulk inserts vs. row-by-row
   - Batch size tuning
   - Memory management for large batches

5. **Async Efficiency**
   - Connection pooling
   - Concurrent request handling
   - Worker concurrency tuning

6. **Monitoring Performance**
   - Response time metrics
   - Query execution times
   - Task processing latency

---

### Testing Theme

#### **Document 19: Testing Strategy**
**File:** `docs/backend/testing/TESTING_STRATEGY.md`

**Content:**

1. **Testing Pyramid** (600 words)
   - Unit tests (40%)
   - Integration tests (50%)
   - E2E tests (10%)
   - Why this distribution?

2. **Unit Testing**
   - Service logic tests (no database)
   - Repository method tests (mocked database)
   - Utility function tests

3. **Integration Testing**
   - Service + Repository tests (real database)
   - Celery task tests
   - Feature-level tests

4. **E2E Testing**
   - Full API workflow tests
   - Authentication flow testing
   - Pipeline execution testing

5. **Test Fixtures & Factories**
   - User fixtures
   - Card data fixtures
   - Database state management between tests

6. **Mocking Strategies**
   - Mocking external APIs (eBay, Shopify, Scryfall)
   - MSW setup for API mocking
   - Database mocking vs. real database tests

7. **CI/CD Integration**
   - Test execution in pipeline
   - Coverage reporting
   - Performance benchmarking

---

#### **Document 20: API Testing Flow**
**File:** `docs/backend/testing/API_TESTING.md`

**Content:**

1. **Manual API Testing Workflow** (400 words)
   - Create test user
   - Authenticate
   - Make API calls
   - Verify responses
   - Cleanup (delete user)

2. **Testing with Authentication**
   - Session cookie handling
   - Auth headers
   - Permission testing

3. **Testing Error Scenarios**
   - 400 Bad Request
   - 401 Unauthorized
   - 403 Forbidden
   - 404 Not Found
   - 500 Server Error

4. **Testing with Tools**
   - cURL examples
   - Postman collection
   - API documentation endpoint (`/docs`)

---

## Diagram Strategy

### Mermaid Diagrams (Text-based, version-control friendly)
- Layered architecture diagram
- Request/response flow sequences
- Celery task flow
- Database entity relationships
- Integration flow diagrams (eBay, Scryfall)
- Error handling flows

### ASCII Diagrams (Simple, readable in plain text)
- Production topology
- Dev topology
- Service discovery flow
- Folder structure

### Image Files (For complex visual content)
- Database schema ERD
- Timeline graphs (pipeline execution)
- Performance benchmark results

---

## Implementation Phases

### Phase 1: Master Index & Architecture (1-2 days)
- Write `docs/BACKEND.md` master index
- Create core Mermaid diagrams (architecture, request flows)
- Write Documents 1-3 (Layered Architecture, Service Discovery, Request Flows)

### Phase 2: Data Layer & Integrations (3-4 days)
- Write Documents 4-6 (Database, Repository, Migrations)
- Write Documents 7-11 (Integration documents)
- Create integration flow diagrams

### Phase 3: Background Jobs & Operations (2-3 days)
- Write Documents 12-14 (Celery, Pipelines, Monitoring)
- Write Documents 15-18 (Logging, Security, Deployment, Performance)

### Phase 4: Testing & Refinement (1-2 days)
- Write Documents 19-20 (Testing Strategy, API Testing)
- Add code examples throughout
- Cross-link between documents

### Phase 5: Validation & Commit
- Review all documents for consistency
- Commit to git with meaningful message

---

## Success Criteria

- [ ] Master index document provides clear navigation
- [ ] All 20 deep-dive documents written with diagrams
- [ ] Every major design decision has documented rationale
- [ ] Code examples demonstrate key patterns
- [ ] Diagrams are clear and useful
- [ ] Documents are organized thematically
- [ ] New developers can understand backend architecture
- [ ] Senior engineers understand trade-offs and alternatives
- [ ] Documents remain synchronized with actual codebase

---

## Known Constraints & Decisions

- **Scope:** Backend only (FastAPI/Celery/PostgreSQL). Frontend and deployment infrastructure docs are separate.
- **Update frequency:** These docs should be updated when major architectural decisions change.
- **Code examples:** Use realistic snippets from actual codebase, not pseudo-code.
- **Rationale:** Every "why" decision should reference trade-offs considered.
- **Existing docs:** Some docs exist (ARCHITECTURE.md, LOGGING.md, etc.). These will be consolidated and enhanced.

---

## Questions for User Review

1. Does this 20-document structure cover everything you need?
2. Are there any subsystems or areas we should add or reorganize?
3. Should we include additional sections on data validation, error codes, or API versioning?
4. Are there existing backend READMEs or inline documentation we should consolidate?

