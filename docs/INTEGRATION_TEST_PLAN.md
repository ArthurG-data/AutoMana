# AutoMana Integration Test Plan

**Author:** Weasel (Integration Testing Master persona, claude-sonnet-4-6)
**Date:** 2026-04-24
**Status:** Approved for implementation
**Target branch:** `feat/mtgjson-pipeline` → `main`

---

## Table of Contents

1. [Overview and Why Integration Tests](#1-overview-and-why-integration-tests)
2. [Tooling and Infrastructure Prerequisites](#2-tooling-and-infrastructure-prerequisites)
3. [Flow Inventory](#3-flow-inventory)
4. [Coverage Targets](#4-coverage-targets)
5. [Test Strategy by Domain](#5-test-strategy-by-domain)
6. [Fixtures and Scaffolding Design](#6-fixtures-and-scaffolding-design)
7. [Phased Rollout](#7-phased-rollout)
8. [Known Bugs and Infrastructure Blockers](#8-known-bugs-and-infrastructure-blockers)
9. [What We Are Deliberately Not Testing](#9-what-we-are-deliberately-not-testing)
10. [Risks and Open Questions](#10-risks-and-open-questions)
11. [Consultations](#11-consultations)

---

## 1. Overview and Why Integration Tests

AutoMana has zero integration tests today. The unit plan (`docs/UNIT_TEST_PLAN.md`) covers service-layer pure logic. Everything the unit plan explicitly defers — routers, repositories, Celery pipeline chains, and external integration boundaries — is this plan's domain.

The 90% integration coverage floor is measured across four axes:

- Every router endpoint: at minimum one happy-path and one failure-path test through the full stack.
- Every public service method invoked from a router or Celery task.
- Every pipeline step, including full chain execution with context propagation verified.
- Every error and retry branch: retry logic at `run_service` level, 4xx/5xx responses, DB constraint violations, external API failures.

### 1.1 Why Integration Tests Specifically

The following are concrete codebase incidents, not abstract arguments. Each one illustrates a bug class that unit tests cannot catch.

**The `df00f5b public_schema_leak_check` regression.** Commit `df00f5b` ("fix(ops): reduce false positives in public_schema_leak_check") corrected a SQL check that flagged extension-owned objects (pgvector, TimescaleDB) as schema leaks. This false positive *only* surfaces against a populated real database schema where `pg_depend` rows for extensions actually exist. Against mocks, the check is trivially correct. An integration test against a real TimescaleDB+pgvector container — with migrations applied and extensions registered — would have caught this before it reached `main`.

**Layered architecture drift.** A typo in a ServiceManager key (e.g., `"intergrations.ebay.selling.listings.create"`) passes every unit test because each layer mocks the next. The same typo produces an unhandled 500 in production on the first real request. Only a test that exercises Router → ServiceManager → ServiceRegistry → Service → Repository → DB catches this class of error.

**Celery step-signature filtering.** The `run_service` dispatcher calls `inspect.signature` on the next step and silently drops any context key not in the signature. Renaming `file_path_prices` to `prices_file_path` in the download step would invisibly break the `stream_to_staging` step — it would receive `None` for its only required parameter and either crash or silently do nothing. Unit tests see no mismatch because they call steps in isolation with explicit kwargs. An integration test that runs the full chain exposes this immediately.

**TimescaleDB hypertable and pgvector behaviour.** `pricing.price_observation` is a TimescaleDB hypertable partitioned by `ts_date` with a 7-day chunk interval and auto-compression after 180 days. Upsert behaviour on compressed chunks, advisory lock semantics, and `COPY`-into-staging performance are all TimescaleDB-specific and cannot be reproduced with SQLite, plain Postgres, or mocks. Similarly, `pgvector` similarity search behaves differently under real index creation. Only tests against a real TimescaleDB+pgvector instance exercise these paths.

**eBay idempotency singleton under real Redis.** `get_idempotency_store()` holds a process-global singleton. The `RedisIdempotencyStore`'s graceful-degradation paths (connection failure → returns None, allows the call through) only fire under real Redis with real connection errors. The unit tests cover this with a mock client. But the integration concern is different: verifying that a second `create_listing` call with the same `idempotency_key` actually returns the Redis-cached result without calling `selling_repository.create_listing` again requires a real Redis with real `NX EX` semantics.

**Auth cookie + JWT refactor (commit `84107ea`).** The refactor separated JWT-in-body from `httponly` session cookie. This is a security-critical boundary. If the cookie flags regress (`httponly` drops, `samesite` becomes `None`), a unit test that mocks the response would not notice. An integration test through `TestClient` can assert `Set-Cookie` headers verbatim.

**Unit plan §9 scope gap.** The unit plan's "deliberately not testing" section explicitly defers: router layer, repository layer, Celery task chains, `card_catalog/*.py` services, `mtg_stock/data_staging.py`, and `shopify/*.py`. Those deferred items are what ships to production uncovered unless integration tests exist. This plan covers exactly that gap.

---

## 2. Tooling and Infrastructure Prerequisites

### 2.1 The Infrastructure Gap

`deploy/docker-compose.test.yml` currently defines only `backend` and `nginx`. It has no Postgres, no Redis, no Celery worker. The integration test suite requires all three. This section specifies what to add and justifies the approach.

### 2.2 Infra Choice: Testcontainers-Python (Primary) + Compose (CI Fallback)

**Decision: testcontainers-python as primary, docker-compose as CI fallback.**

**Why testcontainers-python:**

- Per-session containers guarantee clean state. Each test session starts with a fresh TimescaleDB and Redis instance; migrations are applied once and rolled back per-test inside a transaction (where possible).
- The canonical TimescaleDB + pgvector image is `timescale/timescaledb-ha:pg17-all`. This image bundles both extensions in a single pull — no separate pgvector layer, no version mismatch. This is critical: plain Postgres or the community pgvector image will not reproduce hypertable partitioning, compressed chunk error behaviour, or `pg_advisory_xact_lock` semantics under concurrent streaming.
- `testcontainers[postgres,redis]` requires only Docker on the developer's machine, not a running compose stack. The developer experience for local test runs is `pytest tests/integration/` and nothing more.

**Why compose as CI fallback:**

- Docker-in-Docker on some CI runners (GitHub Actions without DIND mode, certain GitLab setups) can conflict with testcontainers. A compose-based alternative under `deploy/docker-compose.test.yml` that spins up TimescaleDB + Redis as services sidesteps this.
- CI can set `USE_COMPOSE_INFRA=1` to skip testcontainers and connect to compose-provisioned services instead. Fixtures detect this env var and connect to `localhost:5433` (Postgres) and `localhost:6379` (Redis) rather than spawning containers.

**fakeredis scope:**

`fakeredis` is acceptable for narrow unit-adjacent integration tests where Redis behaviour is not the subject of the test (e.g., testing that a service correctly invokes the idempotency store, but not testing the TTL behaviour or NX semantics). For the eBay idempotency test — which is explicitly validating Redis NX semantics and TTL — a real Redis container is required.

### 2.3 Dev Dependencies to Add

Add under `[project.optional-dependencies]` → `integration` (separate from `dev` to avoid pulling heavy containers into the unit test environment):

```toml
[project.optional-dependencies]
integration = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-mock>=3.12",
    "pytest-cov>=5.0",
    "httpx>=0.27",                        # TestClient async support
    "asgi-lifespan>=2.0",                 # proper FastAPI lifespan in tests
    "testcontainers[postgres,redis]>=4.0",
    "fakeredis>=2.21",                    # narrow cases only
    "celery[pytest]>=5.3",               # celery_app fixture + ALWAYS_EAGER toggle
    "respx>=0.20",                        # httpx-based HTTP mocking
    "vcrpy>=6.0",                         # cassette-based mocking for complex flows
    "asyncpg>=0.29",                      # for direct migration runner in fixtures
]
```

Note: `httpx` is already present in the main dependencies per the codebase. Pin the integration version to not conflict.

### 2.4 Coverage Configuration — Separate from Unit Suite

The unit plan sets `fail_under = 80` in `[tool.coverage.run]` with `source = ["src/automana"]`. If integration tests run under the same config, coverage data files collide and the `fail_under` threshold is measured against the wrong suite.

**Solution: separate coverage data files + merge step.**

Add `.coveragerc-integration`:

```ini
[run]
source = src/automana
branch = true
data_file = .coverage.integration
omit =
    src/automana/tools/*
    src/automana/**/migrations/*

[report]
fail_under = 90
show_missing = true
```

The unit suite uses `COVERAGE_FILE=.coverage.unit pytest tests/unit/ --cov`.
The integration suite uses `COVERAGE_FILE=.coverage.integration pytest tests/integration/ --cov --cov-config=.coveragerc-integration`.

Merge both into a combined report:

```bash
coverage combine .coverage.unit .coverage.integration
coverage report --rcfile=.coveragerc-combined
```

The `fail_under` in the merged report reflects the combined posture. Each suite's own `fail_under` is enforced independently in CI, preventing either suite from free-riding on the other's coverage.

### 2.5 pytest Configuration Additions

Add to `pytest.ini`:

```ini
[pytest]
asyncio_mode = auto
markers =
    unit: Unit tests (no DB, no HTTP, no Redis)
    integration: Integration tests (real DB, real Redis, mocked HTTP boundary)
    api: Router + service + repository full-stack tests
    repository: Repository-layer tests (DB only, no router)
    pipeline: Celery pipeline chain tests
    ebay: eBay integration tests (real Redis required)
    slow: Tests expected to run >10s (excluded from default run via -m "not slow")
```

### 2.6 Database Migration Strategy

For each test session:

1. `testcontainers` starts a fresh `timescale/timescaledb-ha:pg17-all` container.
2. A session-scoped fixture applies all migrations under `database/SQL/migrations/` in filename order using `asyncpg` directly.
3. Schemas under `database/SQL/schemas/` are applied first (baseline), then migrations.
4. Each test wraps its DB operations in a transaction and rolls back at teardown. This is the default strategy for CRUD-style tests.
5. Celery pipeline tests that call stored procedures with internal `COMMIT/ROLLBACK` (e.g., `pricing.load_price_observation_from_mtgjson_staging_batched`) **cannot** use transaction rollback because the stored proc issues its own commits. These tests use `TRUNCATE ... CASCADE` between tests instead, scoped to the affected tables.

Verify migrations apply cleanly by asserting the migration runner returns no errors and the `ops.ingestion_runs` table is queryable after setup.

### 2.7 Directory Layout

```
tests/
  conftest.py                      # top-level: shared containers, app lifespan
  unit/                            # (owned by unit test manager — do not add here)
  integration/
    conftest.py                    # integration-only fixtures: DB pool, Redis, TestClient
    api/
      routers/
        test_auth_router.py
        test_users_router.py
        test_catalog_router.py
        test_ebay_router.py
        test_mtg_stock_router.py
        test_ops_router.py
    repositories/
      test_session_repository.py
      test_user_repository.py
      test_card_catalog_repository.py
      test_ops_repository.py
      test_mtgjson_repository.py
    pipelines/
      test_scryfall_pipeline.py
      test_mtgjson_pipeline.py
      test_mtgstock_pipeline.py
      test_signature_drift.py      # meta-test: context key contract enforcement
    services/
      test_ebay_idempotency_redis.py
      test_card_catalog_services.py
      test_mtgstock_data_staging.py
      test_ops_integrity.py
```

---

## 3. Flow Inventory

Every flow listed here must have at minimum one happy-path integration test. Failure paths are noted where they require separate test cases.

### 3.1 Authentication and Session Flows

| Flow | Endpoints touched | Service keys | DB tables | Notes |
|------|-------------------|--------------|-----------|-------|
| Register user | `POST /api/users/users/` | `user.register` | `user_management.users` | Duplicate username → 409 |
| Login — cookie + JWT | `POST /api/users/auth/token` | `auth.auth.login` | `user_management.v_active_sessions` | `Set-Cookie: session_id` httponly assertion |
| Authenticated request via cookie | `GET /api/users/users/me` | `auth.session.read` | `v_active_sessions` | `CurrentUserDep` resolved |
| Session refresh | `POST /api/users/auth/token/refresh` | — | `v_active_sessions` | New JWT in body |
| Logout | `POST /api/users/auth/logout` | `auth.auth.logout` | session delete | Cookie cleared |
| Bearer-token request | `GET /api/users/users/` | `check_token_validity` | — | `Authorization: Bearer <jwt>` path |
| Expired token | `GET /api/users/users/` | `check_token_validity` | — | Returns 401 |
| Schema-qualified sessions table | any session operation | — | `user_management.v_active_sessions` | Verify the schema-qualified name is hit |

### 3.2 User Management Flows

| Flow | Endpoint | Service key | Notes |
|------|----------|-------------|-------|
| Create user | `POST /api/users/users/` | `user.register` | |
| Update user | `PUT /api/users/users/` | `user.update` | |
| Search users (paginated) | `GET /api/users/users/` | `user.search` | PaginatedResponse shape |
| Delete user | `DELETE /api/users/users/{user_id}` | `user.delete` | |
| Assign role | `POST /api/users/users/{user_id}/roles` | `user.role.assign` | Role-not-found → 404 |
| Revoke role | `DELETE /api/users/users/{user_id}/roles/{role_name}` | `user.role.revoke` | |

### 3.3 Card Catalog Flows

| Flow | Endpoint | Service key | Notes |
|------|----------|-------------|-------|
| Insert card | `POST /api/catalog/mtg/card-reference/` | `card.insert` | |
| Get card by id | `GET /api/catalog/mtg/card-reference/{card_id}` | `card.get` | Non-existent → 404 |
| Search cards (paginated) | `GET /api/catalog/mtg/card-reference/` | `card.search` | |
| Bulk insert cards | `POST /api/catalog/mtg/card-reference/bulk` | `card.bulk` | Up to 50 |
| Delete card | `DELETE /api/catalog/mtg/card-reference/{card_id}` | `card.delete` | |
| Create collection | `POST /api/catalog/mtg/collection/` | `collection.create` | Requires session cookie |
| Get collection | `GET /api/catalog/mtg/collection/{collection_id}` | `collection.get` | |
| List collections | `GET /api/catalog/mtg/collection/` | `collection.list` | |
| Update collection | `PUT /api/catalog/mtg/collection/{collection_id}` | `collection.update` | |
| Delete collection | `DELETE /api/catalog/mtg/collection/{collection_id}` | `collection.delete` | |
| Set reference CRUD | `/api/catalog/mtg/set-reference/*` | set service keys | Happy paths |

### 3.4 Scryfall Pipeline Flow

Full 11-step `daily_scryfall_data_pipeline` chain. Individual steps and full chain.

| Step | Service key | Context keys returned | Consumed by |
|------|-------------|----------------------|-------------|
| 1 | `staging.scryfall.start_pipeline` | `ingestion_run_id` | Step 10 (`finish_run`) |
| 2 | `staging.scryfall.get_bulk_data_uri` | `manifest_uri` | Step 3 |
| 3 | `staging.scryfall.download_bulk_manifests` | `manifests` | Step 4 |
| 4 | `staging.scryfall.update_data_uri_in_ops_repository` | `uris_to_download` | Step 7 |
| 5 | `staging.scryfall.download_sets` | `sets_file_path` | Step 6 |
| 6 | `card_catalog.set.process_large_sets_json` | `sets_stats` | — |
| 7 | `staging.scryfall.download_cards_bulk` | `file_path_card` | Step 8 |
| 8 | `card_catalog.card.process_large_json` | `cards_stats` | — |
| 9 | `staging.scryfall.download_and_load_migrations` | — | — |
| 10 | `ops.pipeline_services.finish_run` | — | — |
| 11 | `staging.scryfall.delete_old_scryfall_folders` | `deleted_count` | — |

### 3.5 MTGJson Pipeline Flow

Full 6-step `daily_mtgjson_data_pipeline` chain.

| Step | Service key | Context key returned | Consumed by |
|------|-------------|---------------------|-------------|
| 1 | `ops.pipeline_services.start_run` | `ingestion_run_id` | Step 6 |
| 2 | `mtgjson.data.download.today` | `file_path_prices` | Step 3 |
| 3 | `staging.mtgjson.stream_to_staging` | `rows_staged`, `cards_seen` | — (informational) |
| 4 | `staging.mtgjson.promote_to_price_observation` | *(empty)* | — |
| 5 | `staging.mtgjson.cleanup_raw_files` | `files_deleted` | — |
| 6 | `ops.pipeline_services.finish_run` | — | — |

### 3.6 MTGStock Pipeline Flow

5-step `mtgStock_download_pipeline` chain.

| Step | Service key | Notes |
|------|-------------|-------|
| 1 | `ops.pipeline_services.start_run` | |
| 2 | `mtg_stock.data_staging.bulk_load` | Reads from `root_folder` |
| 3 | `mtg_stock.data_staging.from_raw_to_staging` | `source_name` param |
| 4 | `mtg_stock.data_staging.from_staging_to_prices` | No params — uses whole staging |
| 5 | `ops.pipeline_services.finish_run` | |

### 3.7 eBay Write-Side Listing Flows

| Flow | Service key | Redis required | Notes |
|------|-------------|----------------|-------|
| Create listing (cache miss) | `integrations.ebay.selling.listings.create` | Yes | Writes to Redis after eBay API call |
| Create listing (idempotency hit) | same | Yes | Second call with same key returns cached result |
| Create listing (idempotency key missing) | same | No | Returns 422/ValueError |
| End listing (happy path) | `integrations.ebay.selling.listings.end` | No | |
| End listing (missing item_id) | same | No | Returns 422 |
| Update listing (happy path) | `integrations.ebay.selling.listings.update` | No | |

### 3.8 Ops Integrity Check Flows

| Flow | Service key | Real schema required |
|------|-------------|---------------------|
| Scryfall run diff | `ops.integrity.scryfall_run_diff` | Yes — queries `ops.ingestion_runs` |
| Scryfall integrity | `ops.integrity.scryfall_integrity` | Yes — queries `card_catalog`, `pricing` |
| Public schema leak check | `ops.integrity.public_schema_leak` | Yes — checks `pg_depend` for extension objects |
| False-positive regression test | `ops.integrity.public_schema_leak` | Yes — pgvector + TimescaleDB extensions must be installed |

### 3.9 Signature Drift Regression Flow

A meta-test that verifies the pipeline chain fails fast (not silently) when a context key is renamed.

### 3.10 Celery Retry Behaviour at `run_service` Level

Verify that when a service step raises, `run_service` propagates the failure, the Celery task is marked `FAILED`, and the ops `ingestion_runs` row reflects the failed state. Verify no `autoretry_for` is set on any pipeline task.

---

## 4. Coverage Targets

Coverage targets are per-tier. The 90% integration floor applies to Tier A (router + service + repository for CRUD domains). Other tiers have explicit justifications for lower or different targets.

### 4.1 A Note on Measurement

Integration coverage is measured with branch coverage enabled (`branch = true` in `.coveragerc-integration`). Because the integration tests exercise the full stack, they will also accumulate coverage on service-layer code. This is acceptable and desirable — it is not "stealing" from the unit suite. The two suites measure independent `COVERAGE_FILE` targets; the merged report is informational.

### Tier A — Router + Service + Repository CRUD Domains: >= 90% branch

These are well-bounded, test-friendly domains with no external HTTP dependencies at test time.

| Domain | What drives the 90% target |
|--------|-----------------------------|
| Auth endpoints | Clear happy + failure paths; cookie assertions make this a mandatory integration test |
| Users CRUD | Standard CRUD; all branches exercisable with real DB data |
| Collections CRUD | Requires `session_id` dependency — only integration catches the auth coupling |
| Card catalog CRUD | Repository SQL correctness (upsert on conflict, FK enforcement) only visible against real DB |
| Session repository | Schema-qualified views and stored functions only testable against real schema |
| Ops integrity checks | Read-only SQL against real schema — trivial to cover, high diagnostic value |

### Tier B — Celery Pipeline Critical Paths: Critical paths only, not measured by line coverage on loop bodies

Celery pipeline tests target step start/finish/retry/skip branches and context key propagation. They do not aim for line coverage on `tqdm` loop bodies, `ijson` streaming internals, or pandas chunking paths — those are streaming ETL primitives, not business logic.

| Domain | What is covered | What is excluded |
|--------|----------------|------------------|
| Scryfall pipeline | Full chain end-to-end with mocked HTTP; `start_run`/`finish_run` in ops; `delete_old_scryfall_folders` keep-count; URI-diff skip path | `ijson` streaming internals, tqdm progress, file chunk iteration |
| MTGJson pipeline | Full chain; `stream_to_staging` row count assertion; `promote_to_price_observation` call verified; `check_version` skip vs upsert | `lzma` decompress internals, asyncpg COPY internals |
| MTGStock pipeline | `from_raw_to_staging` → `from_staging_to_prices` with real schema; run status recorded | Stored proc batching internals |
| Signature drift | Explicit regression test verifying mis-named context key causes chain failure | — |
| Retry behaviour | `run_service` retry configuration; ops row status after failure | Celery worker transport internals |

### Tier C — External Integration Boundaries: Happy path + idempotency, HTTP mocked

| Domain | Strategy | Notes |
|--------|----------|-------|
| eBay write-side | Real Redis for idempotency NX semantics; eBay HTTP boundary mocked via `respx` | Must not mock at service method level — mock at HTTP layer only |
| Scryfall HTTP | `respx` cassette or `vcrpy` for bulk manifest and card file download | Assert the service handles `uris_to_download = []` sentinel correctly |
| MTGJson HTTP | `respx` for `AllPricesToday.json.xz` download | Use a real small `.xz` fixture file for stream-decompression path |
| MTGStock | No external HTTP — data comes from filesystem; test against real DB | |
| Shopify | Deferred — see §9 | |

---

## 5. Test Strategy by Domain

### 5.1 Auth Router — Login, Logout, Cookie Assertions

**Stack exercised:** `POST /api/users/auth/token` → Router → `auth.auth.login` service → `SessionRepository` → `user_management.v_active_sessions`.

**Setup:** Real DB with a user row inserted. `TestClient` via `asgi-lifespan`. App lifespan must run (`ServiceManager` initialised, DB pool open).

**Scenarios:**

- Happy path login: correct credentials → response body contains `access_token`; `Set-Cookie` header contains `session_id` with `HttpOnly`, `SameSite=Strict` (and `Secure` outside dev env).
- Wrong password → 401; no `session_id` cookie set.
- Unknown username → 401.
- Logout with valid session cookie → `session_id` cookie cleared (`Max-Age=0` or `expires` in the past).
- Authenticated request via `session_id` cookie → `GET /api/users/users/me` returns current user.
- Authenticated request via `Authorization: Bearer <jwt>` → `GET /api/users/users/` returns paginated users list.
- Expired JWT in Bearer header → 401.
- Session refresh: valid refresh token in cookie → new `access_token` in body.

**Key assertion to add that unit tests cannot:** Verify `Set-Cookie` header contains `HttpOnly` flag. This is trivially missed in any mock-response unit test and catastrophic if it regresses.

**Blocker:** `auth_service.login` has the `get_general_settings` missing-parens bug documented in unit plan §8.1. Until that is fixed, all login-path integration tests are blocked. Do not write workarounds — fix the source.

### 5.2 Auth Router — Dependency Injection Verification

Verify the `CurrentUserDep` dependency resolves correctly through the full stack. The dependency reads the `session_id` cookie, calls the session service, resolves the user, and injects the user object into the route handler.

Test: valid `session_id` cookie → `GET /api/users/users/me` returns `{"user_id": ..., "username": ...}` matching the DB row.
Test: expired/invalid `session_id` → 401.

### 5.3 User Management Router — CRUD End-to-End

**Stack exercised:** Router → `ServiceManager` → user service functions → `UserRepository` → real DB.

**Scenarios:**
- `POST /api/users/users/` with valid payload → 201, user row in DB.
- `POST /api/users/users/` with duplicate username → 409 (or whatever the service raises — verify against real DB unique constraint).
- `GET /api/users/users/` → paginated list; `PaginatedResponse` shape; `pagination.total_count` matches inserted count.
- `PUT /api/users/users/` (authenticated) → updated fields reflected in subsequent GET.
- `DELETE /api/users/users/{user_id}` (admin) → row removed from DB.
- `POST /api/users/users/{user_id}/roles` → role assignment persisted; subsequent GET reflects role.
- `DELETE /api/users/users/{user_id}/roles/{role_name}` → role removed.

### 5.4 Card Catalog Router — CRUD and Bulk Insert

**Stack exercised:** Router → card service → `CardCatalogRepository` → `card_catalog` schema.

**Scenarios:**
- Single insert → GET by ID returns same card.
- Bulk insert (up to 50 cards) → all rows in DB; `successful_inserts` count in response matches.
- Search with `limit=5`, `offset=5` → correct pagination; `has_previous=True`.
- Delete → subsequent GET returns 404.
- Insert with FK violation (set_code not in `card_catalog.sets`) → 422 or controlled error (verify actual behaviour against real DB).

**Specific assertion:** After a card is inserted, verify `card_external_identifier` row exists for the `scryfall_id` if the service writes it. This catches FK-orphan bugs that the `scryfall_integrity` check would surface post-hoc.

### 5.5 Collection Router — Authentication Coupling

Collections require a valid `session_id`. These tests must run with a logged-in session fixture.

**Scenarios:**
- Create collection without `session_id` → 401/403.
- Create collection with valid session → 201; `collection_id` returned.
- Get collection owned by another user → 403 (if ownership is enforced — verify).
- Full lifecycle: create → get → update → delete.

### 5.6 Repository Layer — SQL Correctness

These are repository-only tests that call repository methods directly against a real DB, without going through the router. They are classified as `@pytest.mark.repository` — a sub-tier of integration, not full-stack integration tests.

**`SessionRepository`:**
- `insert_session`: row written to schema-qualified table; `get` returns it.
- `delete` (inactivate): subsequent `get` returns empty/expired.
- Verify the schema-qualified stored function `user_management.insert_add_token` is called (not a bare INSERT — the service uses stored functions per architecture doc).

**`OpsRepository`:**
- `start_run`: `ops.ingestion_runs` row created with correct `pipeline_name`, `source_id`, `run_key`.
- Re-run same `run_key` same day: no duplicate row (ON CONFLICT DO UPDATE behaviour verified).
- `finish_run`: `ended_at` set, `status = 'success'`.
- `update_run`: step row in `ops.ingestion_run_steps` upserted correctly.

**`MtgjsonRepository`:**
- `copy_staging_batch`: rows land in `pricing.mtgjson_card_prices_staging`.
- `acquire_streaming_lock`: advisory lock acquired (second caller in same txn blocks — test with two concurrent connections).

**`CardCatalogRepository`:**
- `add_many` (sets): batch of 5 sets upserted; re-run is idempotent (ON CONFLICT DO NOTHING).
- `add_many` (cards): FK violation on unknown set_code → logged, counted as failed insert, not raised.

### 5.7 Ops Integrity Checks — Against Real Schema

**Why these tests require a real schema:** The `public_schema_leak_check.sql` queries `pg_depend` to exclude extension-owned objects. This join only returns meaningful results when pgvector and TimescaleDB are actually installed and their `pg_depend` rows exist. The false-positive bug fixed in `df00f5b` was that extension-owned sequences and functions were not being excluded. A test that would have caught this: run `public_schema_leak` against a schema where both extensions are installed, assert `error_count == 0` for `unexpected-tables-in-public` even though `vector` and timescaledb objects exist in `public`.

**Scenarios:**
- Run `scryfall_run_diff` against a schema with one completed `scryfall_daily` run → report shape is valid; `check_set == "scryfall_run_diff"`.
- Run `scryfall_integrity` against a clean card catalog → all checks return `severity == "ok"` or `"info"` (no `"error"` rows).
- Run `public_schema_leak` with TimescaleDB and pgvector installed → `error_count == 0`; this is the `df00f5b` regression test.
- Run `public_schema_leak` after intentionally creating a table in `public` → `error_count > 0`; confirms the check catches real leaks.

**Test name for the regression:** `test_public_schema_leak_excludes_extension_objects`.

### 5.8 Scryfall Pipeline — Celery Chain

**Setup:** TimescaleDB container with full schema. `CELERY_TASK_ALWAYS_EAGER = True` for chain execution without a broker. HTTP boundary mocked via `respx` at the `aiohttp`/`httpx` layer.

**Tradeoff of `CELERY_TASK_ALWAYS_EAGER`:** Eager mode executes tasks synchronously in the calling process. This hides broker connectivity issues and serialisation bugs. The tradeoff is accepted for chain correctness tests; a separate test class with a real Redis broker (testcontainers Redis) is used for broker-connectivity and serialisation tests.

**Scenarios:**

- Full chain execution: all 11 steps run; `ops.ingestion_runs` row ends with `status = 'success'`; `ops.ingestion_run_steps` has one row per step.
- `delete_old_scryfall_folders` keep-count enforcement: seed 5 run folders; after chain completes, only 3 remain.
- URI-diff skip path: `update_data_uri_in_ops_repository` returns `uris_to_download = []`; `download_cards_bulk` returns `"NO CHANGES"` sentinel; `card_catalog.card.process_large_json` skips without writing cards.
- Idempotency re-run: run the chain twice with the same `run_key`; second run does not create a duplicate `ops.ingestion_runs` row.
- `start_pipeline` failure: mock the `ops_repository.start_run` to raise; chain fails; no subsequent steps execute.

### 5.9 MTGJson Pipeline — Celery Chain

**Setup:** Same as Scryfall. Provide a real small `.xz`-compressed JSON fixture file (a minimal `AllPricesToday.json.xz` with 3 cards, 2 price observations each) to exercise the streaming decompression path without network access.

**Scenarios:**

- Full chain: `download.today` writes `.xz` to temp dir; `stream_to_staging` COPY loads rows into `pricing.mtgjson_card_prices_staging`; `promote_to_price_observation` calls the stored proc; `cleanup_raw_files` deletes old files; `finish_run` marks success.
- `rows_staged` count matches fixture card count x price observations.
- Advisory lock test: verify `pg_advisory_xact_lock('mtgjson_stream_to_staging')` is acquired by calling `stream_to_staging` and checking `pg_locks` in a concurrent connection.
- `check_version` skip path: `ops_repository.get_mtgjson_resource_version` returns same version as `Meta.json` → `upsert_mtgjson_resource_version` is NOT called; `version_changed = False`.
- `check_version` upsert path: version differs → upsert called; `ops.resources` row updated.

**Context key contract assertion for `file_path_prices`:** The download step returns `{"file_path_prices": ...}`. The `stream_to_staging` step accepts `file_path_prices: str`. Test that renaming the returned key breaks the chain in a detectable way (see §5.11).

### 5.10 MTGStock Pipeline — `data_staging` End-to-End

The unit plan deferred `mtg_stock/data_staging.py` as "thin run-status wrapper; value is at integration layer." This is the integration test for it.

**Setup:** Real DB with `pricing.raw_mtg_stock_price` seeded with 10 test rows (a mix of resolvable and unresolvable `print_id` values). At least one `card_version` row in `card_catalog` with a matching external identifier.

**Scenarios:**
- `from_raw_to_staging`: staging proc `pricing.load_staging_prices_batched` called; resolved rows land in `pricing.stg_price_observation`; unresolved rows in `pricing.stg_price_observation_reject`.
- `from_staging_to_prices`: `pricing.load_prices_from_staged_batched` called; staged rows promoted to `pricing.price_observation`; staging table drained.
- Run tracking: `ops.ingestion_run_steps` has rows for each step with `status = 'success'`.
- Re-run idempotency: running `from_staging_to_prices` again on the same (now empty) staging table is a no-op; no error raised.

### 5.11 Signature Drift Regression Test

This is a meta-test that catches the failure mode described in §1.1 ("Celery step-signature filtering").

**Test structure:** Create a minimal `run_service` chain with two toy services registered under test-only keys:

```python
# Toy step A: returns wrong key name
@ServiceRegistry.register("test.step_a", db_repositories=[])
async def step_a(**kwargs):
    return {"wrong_key": "value"}  # should be "expected_key"

# Toy step B: accepts expected_key
@ServiceRegistry.register("test.step_b", db_repositories=[])
async def step_b(expected_key: str, **kwargs):
    return {"step_b_ran": True}
```

When the chain `step_a | step_b` runs, `run_service` filters the context dict from `step_a` by `step_b`'s signature. Because `wrong_key` is not in `step_b`'s signature, `expected_key` receives no value. `step_b` must fail (TypeError on missing required argument) or execute with a default — either way, the test asserts `step_b_ran` is NOT present in the final result, confirming the dispatcher's behaviour.

Then fix the return key to `"expected_key"` and assert the chain succeeds. This test acts as living documentation of the filtering contract and would catch any future change to how `run_service` filters kwargs.

**Why this is an integration test and not a unit test:** It requires `run_service` to actually execute (the real Celery task, not a mock), which requires Celery eager mode and the real `ServiceManager`.

### 5.12 eBay Idempotency — Real Redis

**Setup:** Real Redis container via testcontainers. `set_idempotency_store(RedisIdempotencyStore(real_redis_client))` in the test fixture.

**Scenarios:**
- First `create_listing` call: Redis has no key → eBay API mocked (returns `{"listing_id": "123"}`); result stored in Redis with NX EX; returned to caller.
- Second `create_listing` call with same `idempotency_key`: Redis has key → eBay API mock is NOT called (assert 0 calls); cached result returned.
- TTL assertion: after Redis key expires (use a 1-second TTL for test), a third call hits the API again.
- Redis connection error during `get`: `RedisIdempotencyStore.get` returns None (graceful degradation); `create_listing` proceeds to API call.
- Redis connection error during `set_if_absent`: warning logged; API result returned to caller anyway.

**Why unit tests cannot cover this:** The NX (set-if-not-exists) atomicity guarantee only exists in real Redis. `fakeredis` implements NX correctly but does not reproduce connection failure semantics. The TTL test requires a real TTL implementation.

### 5.13 Celery Retry and `run_service` Level Behaviour

**Scenarios:**
- Verify that no pipeline task (`daily_scryfall_data_pipeline`, `daily_mtgjson_data_pipeline`, `mtgStock_download_pipeline`) sets `autoretry_for` in its `@shared_task` decorator. This is a static assertion: inspect the decorator kwargs programmatically.
- `run_service` retry test: configure `CELERY_TASK_MAX_RETRIES` to 2 for test; mock a service step to raise on the first two calls and succeed on the third; verify the step result is success and `retry_count` is 2 in the result metadata.
- Final failure recording: mock a step to always raise; after max retries exhausted, assert the Celery task state is `FAILED` and `ops.ingestion_runs.status = 'failed'`.

---

## 6. Fixtures and Scaffolding Design

### 6.1 Top-Level `conftest.py` — Containers and App Lifespan

```python
# tests/conftest.py
import pytest
import asyncio
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

# Session-scoped: one container per test session, not per test.
@pytest.fixture(scope="session")
def timescale_container():
    with PostgresContainer(
        image="timescale/timescaledb-ha:pg17-all",
        username="automana_test",
        password="test_password",
        dbname="automana_test",
        port=5432,
    ) as container:
        yield container

@pytest.fixture(scope="session")
def redis_container():
    with RedisContainer(image="redis:7-alpine") as container:
        yield container
```

The test app must read `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` from env vars set by the container fixture. Use `monkeypatch.setenv` in a session-scoped autouse fixture to point the app at the test containers before `get_settings()` is called.

### 6.2 Integration `conftest.py` — Migration Runner and DB Pool

```python
# tests/integration/conftest.py
import pytest
import asyncpg
import logging

logger = logging.getLogger(__name__)

@pytest.fixture(scope="session")
async def db_pool(timescale_container):
    """Apply all migrations and return a connection pool for tests."""
    # Apply schema files then migrations in filename order.
    # Use asyncpg directly — do not bootstrap the full app for migration.
    pool = await asyncpg.create_pool(timescale_container.get_connection_url())
    await _apply_migrations(pool)
    yield pool
    await pool.close()

async def _apply_migrations(pool):
    """Apply schema SQL files then migration files in order."""
    import pathlib
    base = pathlib.Path("src/automana/database/SQL")
    for sql_file in sorted((base / "schemas").glob("*.sql")):
        await pool.execute(sql_file.read_text())
    for sql_file in sorted((base / "migrations").glob("*.sql")):
        await pool.execute(sql_file.read_text())

@pytest.fixture
async def db_conn(db_pool):
    """Per-test transactional connection. Rolls back after each test."""
    async with db_pool.acquire() as conn:
        tr = conn.transaction()
        await tr.start()
        yield conn
        await tr.rollback()
```

### 6.3 TestClient Fixture

```python
# tests/integration/conftest.py (continued)
import pytest
from httpx import AsyncClient
from asgi_lifespan import LifespanManager
from automana.api.main import app  # the FastAPI app object

@pytest.fixture(scope="session")
async def test_app(timescale_container, redis_container, monkeypatch_session):
    """Start the full FastAPI app with lifespan, pointed at test containers."""
    monkeypatch_session.setenv("DB_HOST", timescale_container.get_container_host_ip())
    monkeypatch_session.setenv("DB_PORT", str(timescale_container.get_exposed_port(5432)))
    # ... set all required env vars
    async with LifespanManager(app):
        yield app

@pytest.fixture
async def client(test_app):
    async with AsyncClient(app=test_app, base_url="http://test") as ac:
        yield ac
```

Note: `monkeypatch` in pytest-asyncio is function-scoped by default. A session-scoped monkeypatch requires either a custom fixture or the `pytest-env` plugin. Document this clearly to avoid fixture scoping bugs.

### 6.4 Authenticated Client Fixture

```python
@pytest.fixture
async def auth_client(client, db_conn):
    """TestClient with a valid session_id cookie pre-set."""
    # Insert a test user into the DB via the repository directly (not the router,
    # to avoid the login bug dependency).
    user_id = await _insert_test_user(db_conn)
    session_id = await _insert_test_session(db_conn, user_id)
    client.cookies.set("session_id", str(session_id))
    yield client
```

### 6.5 Redis Fixture for eBay Tests

```python
@pytest.fixture
def real_redis_client(redis_container):
    import redis
    client = redis.Redis(
        host=redis_container.get_container_host_ip(),
        port=redis_container.get_exposed_port(6379),
        db=1,  # separate DB from any app-level Redis usage
        decode_responses=False,
    )
    yield client
    client.flushdb()

@pytest.fixture
def real_idempotency_store(real_redis_client):
    from automana.core.services.app_integration.ebay._idempotency import (
        RedisIdempotencyStore, set_idempotency_store,
    )
    store = RedisIdempotencyStore(real_redis_client)
    set_idempotency_store(store)
    yield store
    set_idempotency_store(None)
```

### 6.6 Celery Eager Mode Fixture

```python
@pytest.fixture
def celery_eager(celery_app):
    """Force synchronous Celery execution for chain correctness tests."""
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
    )
    yield celery_app
    celery_app.conf.update(
        task_always_eager=False,
        task_eager_propagates=False,
    )
```

`task_eager_propagates = True` is critical: without it, exceptions in eager mode are swallowed into the result object rather than raised, making failure tests unreliable.

### 6.7 MTGJson Fixture File

Create `tests/integration/fixtures/mtgjson/AllPricesToday_minimal.json.xz` — a real lzma-compressed JSON file containing 3 card entries with valid MTGJson price tree structure. This file is committed to the repo. It exercises the full streaming decompression path without network access. Size target: < 5 KB compressed.

### 6.8 HTTP Mocking Fixtures

Use `respx` (httpx-native) for services that use `httpx`. Use `vcrpy` for services that use `aiohttp` (Scryfall streaming download).

```python
@pytest.fixture
def mock_scryfall_api(respx_mock):
    respx_mock.get("https://api.scryfall.com/bulk-data").respond(
        200, json={"data": [{"type": "default_cards", "download_uri": "https://...", ...}]}
    )
    # ... register other Scryfall endpoints
    yield respx_mock
```

All HTTP mocking must be at the HTTP transport boundary — not at the repository method level. The repository's `stream_download` method must actually be called; only the underlying HTTP session is intercepted.

### 6.9 Ops Test Data Seeder

```python
@pytest.fixture
async def seeded_scryfall_run(db_conn):
    """Insert a completed scryfall_daily run for integrity check tests."""
    run_id = await db_conn.fetchval(
        "INSERT INTO ops.ingestion_runs (pipeline_name, source_id, run_key, status, started_at, ended_at) "
        "VALUES ('scryfall_daily', 1, 'scryfall_daily:2026-04-24', 'success', now() - interval '1 hour', now()) "
        "RETURNING id"
    )
    yield run_id
```

---

## 7. Phased Rollout

Phases are ordered by security value, coverage ROI, and dependency order. Each phase is independently mergeable.

### Phase 0 — Infrastructure and Scaffolding (no test logic, no coverage)

**Goal:** CI can run `pytest tests/integration/ -m integration` without error (zero tests collected is acceptable).

**Work items:**
1. Add `integration` optional-dependency group to `pyproject.toml`.
2. Add `asyncio_mode = auto` and `integration` marker to `pytest.ini` (coordinate with unit test manager to avoid breaking the `unit` test run).
3. Create `.coveragerc-integration`.
4. Create `tests/integration/` directory with `__init__.py` files.
5. Write `tests/conftest.py` (container fixtures — session-scoped).
6. Write `tests/integration/conftest.py` (migration runner, DB pool, TestClient, auth_client).
7. Update `deploy/docker-compose.test.yml` with TimescaleDB and Redis services as the CI fallback.
8. Create `tests/integration/fixtures/mtgjson/AllPricesToday_minimal.json.xz`.
9. Verify migration runner applies all current migrations cleanly against a fresh container.

**Deliverable:** `pytest tests/integration/ --co -q` exits 0 with "no tests ran."

**Duration estimate:** 2–3 days of engineering effort. This is the highest-leverage phase — everything else depends on it.

---

### Phase 1 — Auth, Users, and Session Cookie Flow

**Goal:** The security-critical boundary is covered. Cookie regression detection is live.

**Work items:**
1. `tests/integration/api/routers/test_auth_router.py` — login scenarios, cookie header assertions, logout, Bearer token path.
2. `tests/integration/api/routers/test_users_router.py` — full user CRUD through router.
3. `tests/integration/repositories/test_session_repository.py` — schema-qualified stored function assertions.

**Prerequisite:** `auth_service.login` bug (unit plan §8.1) must be fixed before Phase 1 tests can pass.

**Expected coverage after Phase 1:**
- `api/routers/auth.py`: ~90%
- `api/routers/users.py`: ~85%
- `api/repositories/auth/session_repository.py`: ~90%
- `api/services/auth/auth_service.py`: ~80% (login now exercised)

---

### Phase 2 — Ops Integrity Checks + Pipeline Tracking

**Goal:** The `df00f5b` regression is tested. Pipeline start/finish/retry is covered. Any future pipeline can be added with confidence in the ops tracking layer.

**Work items:**
1. `tests/integration/services/test_ops_integrity.py` — all three integrity checks against real schema; `test_public_schema_leak_excludes_extension_objects` regression test.
2. `tests/integration/repositories/test_ops_repository.py` — `start_run`, `finish_run`, `update_run`, re-run idempotency.
3. `tests/integration/pipelines/test_signature_drift.py` — the meta-test.
4. `tests/integration/pipelines/test_scryfall_pipeline.py` — `start_pipeline` + `finish_run` only (defer full chain to Phase 3).

**Expected coverage after Phase 2:**
- `core/services/ops/integrity_checks.py`: ~95%
- `core/repositories/ops/ops_repository.py`: ~80%
- `worker/tasks/pipelines.py` (ops tracking steps): ~60%

---

### Phase 3 — Scryfall, MTGJson, MTGStock Full Pipeline Chains

**Goal:** All three ETL pipelines have full chain execution tests. Context key contracts are verified.

**Work items:**
1. `tests/integration/pipelines/test_scryfall_pipeline.py` — full 11-step chain; skip path; keep-count enforcement.
2. `tests/integration/pipelines/test_mtgjson_pipeline.py` — full 6-step chain; streaming to staging; row count assertion; `check_version` skip/upsert.
3. `tests/integration/pipelines/test_mtgstock_pipeline.py` — `from_raw_to_staging`; `from_staging_to_prices`; run status.
4. `tests/integration/repositories/test_mtgjson_repository.py` — `copy_staging_batch`; advisory lock.
5. `tests/integration/repositories/test_card_catalog_repository.py` — `add_many` sets and cards; FK violation handling.

**Expected coverage after Phase 3:**
- `worker/tasks/pipelines.py`: ~75%
- `core/services/app_integration/mtgjson/data_loader.py`: ~70% (streaming ETL — loop bodies excluded)
- `core/services/app_integration/scryfall/data_loader.py`: ~70%
- `core/services/app_integration/mtg_stock/data_staging.py`: ~85%

---

### Phase 4 — eBay Write-Side with Real Redis

**Goal:** Idempotency key collision against real Redis is tested. eBay listing write-side router is covered.

**Work items:**
1. `tests/integration/services/test_ebay_idempotency_redis.py` — all Redis scenarios including TTL and connection failure.
2. `tests/integration/api/routers/test_ebay_router.py` — create/end/update listing through router with mocked eBay HTTP and real Redis idempotency.

**Expected coverage after Phase 4:**
- `core/services/app_integration/ebay/listings_write_service.py`: ~90%
- `core/services/app_integration/ebay/_idempotency.py` (integration complement to unit): ~85%

---

### Phase 5 — Card Catalog Router and Remaining Endpoints

**Goal:** Card catalog CRUD and collection flows are covered. Integration suite approaches the 90% floor.

**Work items:**
1. `tests/integration/api/routers/test_catalog_router.py` — card and set CRUD; bulk insert; file upload.
2. `tests/integration/api/routers/test_mtg_stock_router.py` — stage, load_ids, load endpoints.
3. `tests/integration/services/test_card_catalog_services.py` — `card_catalog/*.py` service end-to-end.

---

## 8. Known Bugs and Infrastructure Blockers

### 8.1 `auth_service.login` Bug (Carried from Unit Plan §8.1)

**Status:** Active bug. **Blocks:** Phase 1 (all login-path integration tests).

The `settings = get_general_settings` bug means `login` always raises `AttributeError` at runtime. No integration test can assert a successful login response until the fix (`settings = get_general_settings()`) is applied.

**Integration test impact beyond the unit plan:** The bug blocks not just the login test itself but also every downstream test that relies on a `client` fixture with a valid `session_id` cookie, because the fixture itself cannot log in through the router. The workaround is to insert session rows directly via the `db_conn` fixture for Phase 0–1 setup, but the login router path must be unblocked before Phase 1 ships.

### 8.2 `token_service.py` Bugs (Carried from Unit Plan §8.2)

**Status:** Active bugs (duplicate function definition, undefined references). **Blocks:** Any test of the `POST /api/users/auth/token/refresh` endpoint.

Do not write tests for the refresh endpoint until `token_service.py` is rewritten. Document the blocker in `test_auth_router.py` as a skipped test with `@pytest.mark.skip(reason="token_service.py has active bugs — see unit plan §8.2")`.

### 8.3 `deploy/docker-compose.test.yml` Missing Services (Infrastructure Blocker)

**Status:** The current `docker-compose.test.yml` defines only `backend` and `nginx`. There is no Postgres, no Redis, no Celery worker service.

**Impact:** CI cannot run integration tests against compose-provisioned infrastructure without this fix.

**Resolution:** Update `deploy/docker-compose.test.yml` as part of Phase 0 to add:

```yaml
services:
  timescaledb:
    image: timescale/timescaledb-ha:pg17-all
    environment:
      POSTGRES_USER: automana_test
      POSTGRES_PASSWORD: test_password
      POSTGRES_DB: automana_test
    ports:
      - "5433:5432"
    networks:
      - app-network

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    networks:
      - app-network

  celery_worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    environment:
      CELERY_TASK_ALWAYS_EAGER: "true"
    depends_on:
      - timescaledb
      - redis
    networks:
      - app-network
```

This is a **must-fix before Phase 0 is complete**. Without it, the CI fallback path does not exist and every pipeline test depends on testcontainers running inside CI — which hits the Docker-in-Docker risk documented in §10.

### 8.4 `ops.resources` Seed Row for `check_version`

**Status:** Known operational requirement from `docs/MTGJSON_PIPELINE.md`: "The `ops.resources` row with `canonical_key = 'mtgjson.all_printings'` must exist for this service to function. It is not seeded automatically."

**Impact:** `staging.mtgjson.check_version` integration tests will fail with a NOT FOUND error unless the migration runner or test fixture inserts this seed row.

**Resolution:** Add a fixture seed step to `_apply_migrations` in `tests/integration/conftest.py` that inserts the required `ops.resources` row after migrations complete.

---

## 9. What We Are Deliberately Not Testing

This section explicitly lists what the integration suite excludes and cross-references the unit plan. Every omission is intentional.

| What | Why not | Covered where |
|------|---------|---------------|
| `analytics/strategies.py`, `analytics/utils.py` | Pure math and regex parsing — no integration seam to test | Unit plan §5.7, §5.8 |
| `api/services/auth/auth.py` pure functions (`verify_password`, `create_access_token`, etc.) | No external dependencies; integration tests would be unit tests in disguise | Unit plan §5.1 |
| `ebay/_auth_context.py` guard clause branching | Three-branch pure guard; unit tests cover all branches | Unit plan §5.11 |
| `ebay/_idempotency.py` `InMemoryIdempotencyStore` | Fully testable with zero external deps | Unit plan §5.12 |
| `analytics/reporting_services.py` | Single-line wrapper; integration adds no value over unit | Unit plan §9 |
| `tools/tui/*` | TUI tooling; not service layer; no integration seam | Not in scope for either plan |
| `shopify/*.py` | Shopify API schema is not stable; no stable sandbox available for gated testing | Deferred until Shopify sandbox is provisioned. Integration tests will be planned at that time. |
| Router endpoints marked TODO/incomplete in code | Testing unstable API surfaces wastes effort; wait for stable interfaces | These endpoints should be identified per the architecture doc note |
| `worker/celeryconfig.py` Beat schedule correctness | Beat schedule timing is an ops concern, not a correctness concern for integration tests; crontab expressions are trivial | Ops monitoring (not tests) |
| tqdm loop bodies, ijson internals, pandas chunking | Testing Python stdlib internals and third-party ETL primitives adds no value | These are not service logic |
| eBay OAuth flow (full browser redirect cycle) | Requires a real eBay developer sandbox; gated behind external credential availability | Deferred; mock the OAuth token exchange in the listing tests |
| TimescaleDB compression and decompression of old chunks | Requires seeding data older than 180 days and triggering compression; extremely slow | Considered an ops concern; the staging-within-compression-window constraint is documented in MTGSTOCK_PIPELINE.md |
| Language features and framework internals | We do not test that FastAPI routes work, asyncpg connects, or Celery executes tasks | |

**Cross-reference with unit plan §9:** The unit plan's "not testing" list (router layer, repository layer, Celery task chains, `card_catalog/*.py`, `mtg_stock/data_staging.py`, `shopify/*.py`) is precisely this plan's scope — with the exception of `shopify/*.py` which both plans defer, and the pure-logic exclusions above.

---

## 10. Risks and Open Questions

### Risk 1 — Test Suite Execution Time

Integration tests with real containers, real DB, and real network-mocked HTTP will be slow. Benchmarks from comparable setups suggest:

- Container startup (TimescaleDB + Redis): 15–30 seconds per session.
- Migration application: 5–15 seconds per session.
- Auth + users test class: 10–20 seconds.
- Full pipeline chain test (Scryfall, 11 steps, eager mode): 30–120 seconds depending on card file fixture size.
- MTGJson pipeline (with minimal fixture): 10–30 seconds.

**Target:** Full integration suite in < 5 minutes. Auth + users marker subset (`-m api and not slow`) in < 30 seconds.

**Mitigations:**
- Use `scope="session"` for container fixtures — start once per session, not per test.
- Exclude `@pytest.mark.slow` tests from the default CI run; run them nightly.
- Use `xdist` (`pytest-xdist`) for parallel test execution, with careful port isolation.

### Risk 2 — CI Concurrency and Port Conflicts

If two branches run integration suites in parallel on the same CI runner, testcontainers will start containers on random ports (avoiding conflicts), but the compose-fallback approach uses fixed ports (`5433`, `6379`). Two parallel compose stacks will conflict.

**Mitigation:** CI must run integration tests with `--forked` isolation or on separate runners. If compose is used in CI, configure `COMPOSE_PROJECT_NAME` per branch to namespace the network and container names. Prefer testcontainers in CI to avoid this problem entirely.

### Risk 3 — Secrets Handling

`core/settings.py` reads `.env.{ENV}` at import time. A test run on a machine with a populated `.env.dev` will pick up real database URLs, real JWT secrets, and potentially real eBay API credentials.

**Mitigation:**
- The test env must set `ENV=test` and provide all required settings via `ENV=test` + a `.env.test` file that contains only fake/test credentials.
- `.env.test` must be committed to the repo (it contains only test credentials, no production secrets).
- `.env` (production values) must never be loaded in test context. Assert in CI that `ENV` is set to `test` before the test suite runs.
- The `monkeypatch.setenv` in container fixtures must override `DB_HOST`, `DB_PORT`, etc. before the settings object is first accessed (before `get_settings()` is called).
- Add a guard to `tests/integration/conftest.py`: `assert os.getenv("ENV") == "test", "ENV must be 'test' for integration tests"`.

### Risk 4 — `CELERY_TASK_ALWAYS_EAGER` Hiding Serialisation Bugs

Eager mode executes tasks in-process, bypassing serialisation (JSON/pickle), the broker, and the result backend. A service that works in eager mode may fail in production because its return value is not JSON-serialisable (e.g., contains `datetime` objects, `Decimal`, or custom classes without `default=str`).

**Mitigation:** Add a separate `@pytest.mark.slow` test class for each pipeline that runs against a real Redis broker (testcontainers Redis, not eager mode). This is limited to one test per pipeline to control runtime. The eager tests cover chain correctness; the real-broker test covers serialisation.

### Risk 5 — Coverage Double-Counting

Integration tests exercise service-layer code, producing coverage data on files that the unit plan also targets. If a CI step merges both coverage files and applies the unit plan's `fail_under = 80` threshold, the integration suite's coverage is double-counted, making the combined threshold trivially easy to meet — and hiding genuine unit-level gaps.

**Mitigation:** The separate `.coveragerc-integration` with `COVERAGE_FILE=.coverage.integration` ensures the two suites are measured independently. The CI pipeline must enforce each suite's threshold separately before merging. The merged report is informational only.

### Risk 6 — eBay and Shopify Sandbox Availability

Phase 4 mocks eBay at the HTTP boundary. If real eBay sandbox calls are ever needed (e.g., for OAuth callback testing), they require eBay developer account credentials that cannot be committed. Shopify sandbox testing is explicitly deferred.

**Mitigation:** All tests in the integration plan mock external HTTP at the transport layer (`respx`, `vcrpy`). No test requires a live eBay or Shopify connection. Tests that would require real credentials are marked `@pytest.mark.skip(reason="requires eBay sandbox credentials")` until a secrets injection mechanism is in place.

### Open Question 1 — `asgi-lifespan` Compatibility with `asyncio_mode = auto`

`asgi-lifespan`'s `LifespanManager` is an async context manager. Under `asyncio_mode = auto`, session-scoped async fixtures have documented edge cases in pytest-asyncio 0.23+. Verify that `LifespanManager` can be used as a session-scoped async fixture without a dedicated event loop fixture.

If it cannot, the fallback is to use a function-scoped `LifespanManager` (slower, starts the app for each test function) or to use a pytest plugin like `anyio` with a shared event loop.

### Open Question 2 — `runs_in_transaction=False` Services and Rollback Strategy

Services registered with `runs_in_transaction=False` (e.g., `staging.mtgjson.promote_to_price_observation`, which calls a stored proc with internal `COMMIT`) cannot use the per-test transaction rollback strategy. After such a test, the staging and prices tables will contain committed rows.

For these tests, use `TRUNCATE pricing.mtgjson_card_prices_staging, pricing.price_observation CASCADE` in the test teardown (after each test in the class, not after each function). Verify this is fast enough (< 1 second for test-volume data) before committing to this strategy.

### Open Question 3 — `monkeypatch` Session Scope Limitation

`monkeypatch` in pytest is function-scoped by default. The test container fixtures that set `DB_HOST`, `DB_PORT`, etc. need to set these env vars before the app's `get_settings()` is called — which happens at session startup. This requires either:
- A session-scoped monkeypatch (non-trivial to implement correctly with pytest-asyncio).
- Setting env vars before session starts (e.g., via `pyproject.toml` `[tool.pytest.ini_options]` `env` key using `pytest-env`).
- Accepting that the app will try to connect to `localhost:5433` and using compose to put a TimescaleDB there.

This must be resolved in Phase 0 before any other fixture can work.

---

## 11. Consultations

### Sub-Agent Consultation Attempt

This plan was designed to include consultation with specialist sub-agents (fox unit tester, automana-db-expert, quality-guardian). The invocation harness available in this session does not provide the `Task` tool required to spawn sub-agents from persona files. Rather than fabricating a consultation, the plan incorporates self-review under each persona's declared perspective.

### Coordination with Fox (Unit Test Manager)

The boundary negotiated with the unit test manager persona is:

- **Unit plan owns:** pure-logic functions, mocked-repo service tests, in-memory idempotency store, isolated ETL row-transformation logic (`_iter_card_rows`, `check_version` branch logic, `delete_old_scryfall_folders` sort logic).
- **Integration plan owns:** router → DB full-stack, repository SQL correctness, Celery chain context propagation, real Redis idempotency, real TimescaleDB hypertable behaviour.
- **Shared coverage (intentional):** The integration suite will accumulate coverage on service-layer files that the unit plan also covers. This is not duplication — it is verification that the full-stack call path exercises the same code. The two suites use separate `COVERAGE_FILE` values; thresholds are enforced independently.

**Items delegated to unit test manager for coordination:**
- `auth_service.login` bug fix: the unit plan documents this (§8.1). The integration plan depends on the fix for Phase 1. Coordinate on fix priority.
- `token_service.py` rewrite: both plans defer tests until the rewrite is complete. Neither plan should unblock the other by papering over the bug.
- Service registry import-time side effects (unit plan risk 1): if the `@ServiceRegistry.register` decorator has global mutable state that leaks across tests, this affects both unit and integration test isolation. Resolution must be coordinated.

### Self-Review in the Automana-DB-Expert Persona

Concerns from a database specialist's perspective:

1. **The `ops.resources` seed row blocker (§8.4) is real.** The doc says it must be inserted manually or via a migration. For integration tests, the migration runner must seed it — or the fixture must insert it. The current plan handles this in `_apply_migrations`. Confirm the seed SQL is idempotent (`INSERT ... ON CONFLICT DO NOTHING`) so re-running migrations against an existing DB is safe.

2. **TimescaleDB hypertable TRUNCATE behaviour.** `TRUNCATE pricing.price_observation CASCADE` on a hypertable with compressed chunks may behave differently than expected. Verify that test data is always within the active (uncompressed) time window, i.e., `ts_date >= now() - interval '180 days'`. Test fixtures must use current dates, not historical dates.

3. **`pg_advisory_xact_lock` in tests.** The advisory lock on `mtgjson_stream_to_staging` is transaction-scoped. In tests using the transaction rollback strategy, the lock is held for the duration of the test's wrapping transaction. Concurrent tests that exercise `stream_to_staging` will block on each other. Either run `stream_to_staging` tests serially (not in parallel with `xdist`) or scope them to a dedicated test class with `scope="class"` serialisation.

4. **The `auth_repository.py` uses schema-qualified stored functions.** The session insert goes through `user_management.insert_add_token`. The migration runner must apply the `user_management` schema SQL before the session repository tests run. Verify migration order: `user_management` schema must precede `ops` schema in the migration sequence.

### Self-Review in the Quality-Guardian Persona

Structural and quality concerns:

1. **Phase 0 is often underestimated.** The hardest part of an integration test suite is not the tests — it is the infrastructure. Phase 0 must ship before any test is written. If Phase 0 is not working in CI, no downstream phase is trustworthy.

2. **The signature-drift test in §5.11 is the highest-value test in the plan.** It documents a real failure mode that is invisible to both unit tests and manual QA. It should be in Phase 2, not Phase 3 — it does not depend on any external service and should be cheap to implement once the Celery fixture is in place.

3. **The `test_public_schema_leak_excludes_extension_objects` test name is exactly right.** It names the precise regression it prevents. Test names should be this specific. Encourage this naming pattern in the test writing phase.

4. **Beware of `scope="session"` fixtures with mutable state.** The `real_idempotency_store` fixture (§6.5) calls `set_idempotency_store(None)` in teardown. If it is session-scoped and a test leaves the store in a dirty state, subsequent tests in the same session will see stale data. Make it function-scoped.

5. **The Celery `task_eager_propagates` setting is non-obvious.** Document why it must be `True` in the fixture comment. Future maintainers who remove it will spend hours debugging silent swallowed exceptions in pipeline tests.
