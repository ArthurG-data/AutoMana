# AutoMana Unit Test Plan

**Author:** Fox (Unit Testing Master persona, claude-sonnet-4-6)  
**Date:** 2026-04-24  
**Status:** Approved for implementation  
**Target branch:** `feat/mtgjson-pipeline` → `main`

---

## Table of Contents

1. [Overview and Goals](#1-overview-and-goals)
2. [Tooling and Infrastructure Prerequisites](#2-tooling-and-infrastructure-prerequisites)
3. [Service Inventory](#3-service-inventory)
4. [Coverage Targets](#4-coverage-targets)
5. [Test Strategy by Domain](#5-test-strategy-by-domain)
6. [Fixtures and Scaffolding Design](#6-fixtures-and-scaffolding-design)
7. [Phased Rollout](#7-phased-rollout)
8. [Known Bugs Blocking Tests](#8-known-bugs-blocking-tests)
9. [What We Are Deliberately Not Testing](#9-what-we-are-deliberately-not-testing)
10. [Risks and Open Questions](#10-risks-and-open-questions)
11. [Consultations](#11-consultations)

---

## 1. Overview and Goals

The AutoMana service layer has **zero unit tests today**. This plan charts the path from
greenfield to a test suite that:

- Exceeds **90% line and branch coverage** on pure-logic modules
- Delivers **critical-path coverage** on orchestration-heavy services where 90% is
  unrealistic without testing infrastructure code
- Runs in **under 10 seconds total** (no real DB, no real HTTP, no real Redis)
- Establishes **reusable fixtures and patterns** that make adding the next test a
  three-minute task, not a thirty-minute archaeology dig

The unit tests do not replace integration tests. Repository-layer correctness and
Celery pipeline end-to-end behaviour are out of scope here. This plan covers the
**service layer only**: `src/automana/api/services/` and `src/automana/core/services/`.

---

## 2. Tooling and Infrastructure Prerequisites

### 2.1 Missing Dev Dependencies

The following packages are **not** in `pyproject.toml` and must be added before any test
can run. Add them under `[project.optional-dependencies]` → `dev` (or equivalent):

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",   # async test functions and async fixtures
    "pytest-mock>=3.12",      # mocker fixture (wraps unittest.mock cleanly)
    "pytest-cov>=5.0",        # coverage reporting
]
```

Verify installation with:

```
pip install -e ".[dev]"
pytest --co -q  # collection smoke-test, zero tests expected at first
```

### 2.2 pytest.ini Changes Required

`pytest.ini` exists but is missing two critical settings:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto          # ADD THIS — eliminates @pytest.mark.asyncio boilerplate
markers =
    unit: Unit tests
    integration: Integration tests
    api: API tests
    repository: Repository tests
    service: Service tests
```

`asyncio_mode = auto` means every `async def test_*` is automatically treated as an
asyncio test. Without it, async tests silently pass as no-ops under pytest-asyncio 0.21+.

### 2.3 Coverage Configuration

Add a `[tool.coverage.run]` section to `pyproject.toml`:

```toml
[tool.coverage.run]
source = ["src/automana"]
omit = [
    "src/automana/worker/*",        # Celery bootstrap — integration territory
    "src/automana/tools/*",         # TUI tooling — not service layer
    "src/automana/api/routers/*",   # Router layer — api tests cover these
    "src/automana/**/migrations/*",
]
branch = true

[tool.coverage.report]
fail_under = 80   # floor for the suite as a whole; per-module targets in §4
show_missing = true
```

Run coverage with:

```
pytest tests/unit/ --cov --cov-report=term-missing -m unit
```

### 2.4 Directory Layout

```
tests/
  conftest.py                  # top-level fixtures shared across all domains
  unit/
    conftest.py                # unit-test-only fixtures (no DB, no HTTP)
    api/
      services/
        auth/
          test_auth.py
          test_auth_service.py
          test_session_service.py
        user_management/
          test_user_service.py
          test_role_service.py
    core/
      services/
        analytics/
          test_strategies.py
          test_utils.py
        ops/
          test_integrity_checks.py
          test_pipeline_services.py
        app_integration/
          ebay/
            test_auth_context.py
            test_idempotency.py
            test_listings_write_service.py
          mtgjson/
            test_data_loader.py
            test_pipeline.py
          scryfall/
            test_data_loader.py
```

---

## 3. Service Inventory

### 3.1 `src/automana/api/services/`

| Module | Registered Keys | Test file | Notes |
|--------|-----------------|-----------|-------|
| `auth/auth.py` | — (pure functions) | `test_auth.py` | Zero external deps; highest ROI |
| `auth/auth_service.py` | `auth.auth.logout`, `auth.auth.login` | `test_auth_service.py` | BUG in `login` — see §8 |
| `auth/session_service.py` | `auth.session.delete`, `auth.session.read` | `test_session_service.py` | Mix of registered + private fns |
| `auth/token_service.py` | — | DEFERRED | BUG: duplicate fn def, undefined refs — see §8 |
| `auth/cookie_utils.py` | — | DEFERRED | Thin wrapper; test after bugs fixed |
| `user_management/user_service.py` | `user.register`, `user.update`, `user.search`, `user.delete` | `test_user_service.py` | Error branch coverage |
| `user_management/role_service.py` | `user.role.assign`, `user.role.revoke` | `test_role_service.py` | Role-not-found guard |

### 3.2 `src/automana/core/services/`

| Module | Registered Keys | Test file | Notes |
|--------|-----------------|-----------|-------|
| `analytics/strategies.py` | — (classes, no registry) | `test_strategies.py` | Pure math; parametrize-friendly |
| `analytics/utils.py` | — (pure functions) | `test_utils.py` | Regex parsing; trivial to parametrize |
| `analytics/reporting_services.py` | `analytics.daily_summary` | DEFERRED | Single-line wrapper; coverage via mocking trivial but low value |
| `ops/integrity_checks.py` | 3 ops keys | `test_integrity_checks.py` | `_build_report` is pure; 3 services are thin repo wrappers |
| `ops/pipeline_services.py` | `ops.pipeline_services.start_run`, `.finish_run` | `test_pipeline_services.py` | `track_step` async ctx manager — 3 paths |
| `app_integration/ebay/_auth_context.py` | — (helper) | `test_auth_context.py` | Guard clause — 3 branches |
| `app_integration/ebay/_idempotency.py` | — (module + classes) | `test_idempotency.py` | Protocol, in-memory store, Redis store, singleton lifecycle |
| `app_integration/ebay/listings_write_service.py` | 3 listing keys | `test_listings_write_service.py` | Idempotency hit/miss, guard clauses |
| `app_integration/mtgjson/data_loader.py` | multiple | `test_data_loader.py` | `_iter_card_rows` is richest branch target |
| `app_integration/mtgjson/pipeline.py` | `mtgjson.check_version` | `test_pipeline.py` | Skip vs upsert branching |
| `app_integration/scryfall/data_loader.py` | scryfall pipeline steps | `test_data_loader.py` | `delete_old_scryfall_folders` sort logic |
| `app_integration/mtg_stock/data_staging.py` | mtgstock staging | DEFERRED | Thin run-status wrapper; low unit test value vs integration |
| `app_integration/shopify/collection_service.py` | shopify.collection | DEFERRED | Shopify tests require stable external schema — defer |
| `card_catalog/*.py` | card, collection, set services | DEFERRED | Thin repo wrappers; value is at integration layer |

---

## 4. Coverage Targets

Coverage expectations are **per-module**, not a single project-wide number. A flat
project-wide target would be gamed by piling tests on trivial getters while leaving
complex branching logic untouched.

### A Note on the Tier 1 Floor

The plan sets Tier 1 at >= 90% rather than the 85% floor referenced in the advisor
review. The reasoning: pure-logic modules with no external dependencies (no IO, no
network, no process state) have no credible excuse for missing branches. The only
unreachable lines in these modules are defensive `else` clauses on conditions that the
type system already guarantees. Setting 85% for pure-logic code would permit lazy
coverage without justification. The 90% floor is deliberately set above advisor
guidance for this tier specifically, and the justification is on record here. Tier 2
and below adopt 85% where orchestration noise genuinely limits achievable coverage.

### Tier 1: Pure Logic — Target >= 90% line + branch

These modules have zero external dependencies and full branchability:

| Module | Why 90%+ is realistic |
|--------|-----------------------|
| `api/services/auth/auth.py` | 5 pure functions; no IO |
| `core/services/analytics/strategies.py` | Pure math on dicts; all branches testable |
| `core/services/analytics/utils.py` | Regex parsing on strings |
| `core/services/ops/integrity_checks.py` | `_build_report` is pure; 3 services mock one repo call each |
| `core/services/app_integration/ebay/_auth_context.py` | 3-branch guard clause |
| `core/services/app_integration/ebay/_idempotency.py` | In-memory store fully testable; Redis store via mock client |

### Tier 2: Service Logic with Mocked Repos — Target >= 85% line + branch

These have real branching but depend on injected repositories:

| Module | What reduces coverage below 90% |
|--------|----------------------------------|
| `api/services/auth/auth_service.py` | Unreachable defensive branches after bug fix; `check_token_validity` needs Request mock |
| `api/services/auth/session_service.py` | Mixed sync/async; `insert_session` has a `print()` call and branching on raw DB results |
| `api/services/user_management/user_service.py` | Exception re-raise patterns have multiple exit paths |
| `core/services/ops/pipeline_services.py` | `track_step` 3-path ctx manager + 2 thin registered services |
| `core/services/app_integration/ebay/listings_write_service.py` | Cache encode failure path requires TypeError injection |
| `core/services/app_integration/mtgjson/pipeline.py` | `check_version` two-path branch |

### Tier 3: Orchestrators — Critical-Path Coverage Only

These are streaming ETL orchestrators with tqdm loops, pandas IO, or heavy Celery
glue. Targeting 90% would require mocking the entire Python stdlib. Instead, test
the branches that protect against data corruption or silent failures:

| Module | Critical paths to cover | Deliberately excluded |
|--------|--------------------------|-----------------------|
| `mtgjson/data_loader.py` — `_iter_card_rows` | non-dict card, missing `paper` key, bad date/price cell, happy path | tqdm loop body; pandas concat internals |
| `mtgjson/data_loader.py` — `cleanup_raw_files` | bulk override, sliding window, empty list | StorageService internals |
| `mtgjson/data_loader.py` — `stream_to_staging` | lock-held, batch loop entry | tqdm progress, pandas chunking |
| `scryfall/data_loader.py` — `download_cards_bulk` | empty URI list, no matching type, matched | HTTP streaming |
| `scryfall/data_loader.py` — `delete_old_scryfall_folders` | empty list, keep-count boundary | filesystem operations |

### Tier 4: Deferred

- `token_service.py` — has active bugs (see §8); test after fix
- `analytics/reporting_services.py` — single-line wrapper; not worth mocking
- `shopify/*.py` — Shopify API schema unstable; defer to integration layer
- `mtg_stock/data_staging.py` — thin run-status wrapper; value is at integration layer
- `card_catalog/*.py` — pure repo wrappers; value is at integration layer

---

## 5. Test Strategy by Domain

### 5.1 `auth/auth.py` — Pure JWT and Password Functions

No mocks required. Tests are synchronous.

**Scenarios to cover:**
- `verify_password`: correct password returns True, wrong password returns False
- `get_hash_password`: output is not the plaintext; `verify_password(plain, hash)` returns True
- `create_access_token`: returned token decodes to expected `sub` and `user_id`; expired token raises `ValueError` on decode
- `decode_access_token`: expired token raises `ValueError("Token expired")`; tampered signature raises `ValueError("Invalid token")`; valid token returns payload dict

**What to avoid:** Do not test that PyJWT exists or that bcrypt hashes look like bcrypt hashes. Test the contract of these functions as used by the auth flow.

---

### 5.2 `auth/auth_service.py` — Login, Logout, Token Check

Mock: `UserRepository`, `SessionRepository`, `get_general_settings`.

**`authenticate_user` scenarios:**
- User not found: repository returns None → function returns None
- Wrong password: repository returns user record with wrong hash → returns None
- Correct credentials: returns `UserInDB` instance

**`check_token_validity` scenarios:**
- No Authorization header → raises `HTTPException(401)`
- Header present but no `Bearer ` prefix → raises `HTTPException(401)`
- Valid Bearer token → returns decoded payload dict
- Expired/invalid Bearer token → raises `HTTPException(401)`

**`logout` scenarios:**
- Session found after invalidation → returns `{"status": "success", ...}`
- Session not found after invalidation → returns `{"status": "error", ...}`

**`login` scenarios:** BLOCKED until `settings = get_general_settings` bug is fixed (see §8).

---

### 5.3 `auth/session_service.py` — Session CRUD

Mock: `SessionRepository`, `UserRepository`.

**`validate_session_credentials` scenarios:**
- Repository raises exception → wraps and raises `SessionError`
- Session is expired → raises `SessionExpiredError`
- Valid session → returns session dict

**`get_user_from_session` scenarios:**
- Session has no `user_id` → raises `SessionUserNotFoundError`
- `user_repository.get_by_id` returns None → raises `UserSessionNotFoundError`
- Happy path → returns user dict

**`validate_token_and_get_session_id` scenarios:**
- `decode_access_token` returns falsy payload → raises `InvalidTokenError`
- Payload missing `session_id` → raises `InvalidTokenError`
- Session not in repository → raises `SessionNotFoundError`
- Valid token + existing session → returns UUID

---

### 5.4 `auth/session_service.py` — Registered Services (delete_session, read_session)

The registered service surface of this module was covered in §5.3 for the internal
helpers. Add these scenarios for the two registered functions specifically:

**`delete_session` (`auth.session.delete`):**
- Happy path: `session_repository.delete(ip_address, user_id, session_id)` is called
  with the exact three arguments passed in; no return value to assert (function returns `None`)

**`read_session` (`auth.session.read`):**
- Session found: `session_repository.get(session_id)` returns a non-empty list →
  service returns it
- Session not found: `session_repository.get(session_id)` returns `None` →
  service returns `None`; `logger.error` is called (verify via `caplog` or mocker)

---

### 5.5 `user_management/user_service.py` — User CRUD Services

Mock: `UserRepository`.

**`register` scenarios:**
- Happy path: repository creates user, returns new user record
- Duplicate username: repository raises (e.g., `IntegrityError` or equivalent) →
  service raises or returns error response (verify actual behavior before writing)
- Invalid input (missing required fields): Pydantic validation or service-level guard raises

**`update` scenarios:**
- User not found: repository returns `None` or raises → service raises expected error
- Valid update: repository called with correct payload, updated record returned

**`search_users` scenarios:**
- Empty search results: repository returns empty list → service returns empty list
- Matching results: repository returns list of user dicts → service returns same

**`delete_user` scenarios:**
- User not found: repository returns falsy → service raises or returns error response
- Happy path: repository called with user_id, deletion confirmed

---

### 5.6 `user_management/role_service.py` — Role Assignment

Mock: `RoleRepository` (or whichever repository the service injects).

**`assign_role` scenarios:**
- Role not found: repository lookup returns `None` → service raises (verify exception type)
- Happy path: role exists, repository called with `(user_id, role_id)`, result returned

**`revoke_role` scenarios:**
- Role not found or not assigned: repository returns falsy → service raises or returns error
- Happy path: repository called with correct args, revocation confirmed

**Note:** Read `role_service.py` before writing these tests to confirm the exact exception
types and return shapes. The inventory scan identified error-branch coverage as the goal
but did not record the specific exception classes.

---

### 5.7 `analytics/strategies.py` — Pricing Strategies

No mocks. Tests are synchronous. Use `@pytest.mark.parametrize` aggressively.

**`QuickSaleStrategy.calculate_price` scenarios:**
- High volatility market (`volatility > 0.3`) → price is `p25 * 0.95`, confidence is 0.9
- Normal market → price is `p25`, confidence is 0.85
- `market_data=None` → no KeyError; uses default volatility 0

**`QuickSaleStrategy.is_suitable` scenarios:**
- `inventory_level == 'high'` → True
- `cash_flow_priority == True` → True
- `volatility > 0.3` → True
- None of the above → False

Apply the same parametrize pattern to `CompetitiveStrategy` and `PremiumStrategy`.

**`PricingStrategyManager.recommend_strategy` scenarios:**
- No suitable strategies (impossible with `CompetitiveStrategy` present, but test by mocking all strategies' `is_suitable` to return False) → falls back to competitive
- Multiple suitable strategies → returns highest-confidence one

**Note:** `CompetitiveStrategy.is_suitable` always returns True, making the "no suitable strategy" path only reachable if the manager is constructed without `CompetitiveStrategy`. That is a real design constraint the test must document by constructing a manager with only `PremiumStrategy`.

---

### 5.8 `analytics/utils.py` — Condition Parsing

No mocks. Synchronous. Ideal for `@pytest.mark.parametrize`.

**`parse_title_for_condition` parametrize table:**

```python
@pytest.mark.parametrize("title,expected", [
    ("NM foil",           "Near Mint"),
    ("Near Mint",         "Near Mint"),
    ("lp",                "Lightly Played"),
    ("Lightly Played",    "Lightly Played"),
    ("MP",                "Moderately Played"),
    ("hp",                "Heavily Played"),
    ("Damaged",           "Damaged"),
    ("PSA 10",            "Graded"),
    ("Sealed booster",    "Sealed"),
    ("",                  "Unknown"),
    (None,                "Unknown"),  # none guard
    ("random text",       "Unknown"),  # no match fallback
    ("MINT condition",    "Near Mint"),
    ("beat up",           "Heavily Played"),  # inference pattern
])
```

Cover `parsed_description_for_condition` with a subset of the same inputs — it shares
the same core logic.

---

### 5.9 `ops/integrity_checks.py` — Report Building and Service Wrappers

**`_build_report` (pure function):**
- Empty rows list → all counts zero, all lists empty
- Rows with mixed severities → correct partition into errors/warnings/passed
- All errors → `error_count == total_checks`, `passed` and `warnings` empty
- Row counts in returned dict match partitioned lists

**Three service functions (`scryfall_run_diff`, `scryfall_integrity`, `public_schema_leak`):**
- Each: mock the relevant `OpsRepository` method to return a list of fixture rows; assert the service calls the correct method and returns `_build_report`'s output.
- One test per service is sufficient — they are all the same one-liner pattern. Do not write three copies of the same test.

---

### 5.10 `ops/pipeline_services.py` — `track_step` Context Manager

`track_step` has three distinct execution paths that must all be tested:

**Path 1 — No-op (None inputs):**
```python
async with track_step(None, None, "step_name"):
    pass  # must not raise, must not call any repository method
```

**Path 2 — Success:**
```python
mock_repo = AsyncMock()
async with track_step(mock_repo, 42, "ingest_cards"):
    pass
# assert update_run called twice: once with status="running", once with status="success"
```

**Path 3 — Exception propagation:**
```python
mock_repo = AsyncMock()
with pytest.raises(ValueError):
    async with track_step(mock_repo, 42, "ingest_cards", error_code="bad_data"):
        raise ValueError("boom")
# assert update_run called with status="failed" and error_details containing "boom"
# assert the ValueError is re-raised (not swallowed)
```

**`start_run` service:**
- Happy path: `ops_repository.start_run` returns int → service returns `{"ingestion_run_id": int}`
- Exception: repository raises → service re-raises (logger.error coverage)

**`finish_run` service:**
- Happy path: `ops_repository.finish_run` called with correct args; no return value checked

---

### 5.11 `ebay/_auth_context.py` — `resolve_token` Guard Clause

Three branches, three tests:

```python
async def test_resolve_token_raises_on_empty_app_code():
    with pytest.raises(ValueError, match="app_code is required"):
        await resolve_token(mock_repo, user_id=uuid4(), app_code="")

async def test_resolve_token_raises_when_no_token_found():
    mock_repo.get_valid_access_token.return_value = None
    with pytest.raises(ValueError, match="No valid eBay access token"):
        await resolve_token(mock_repo, user_id=uuid4(), app_code="APP1")

async def test_resolve_token_returns_token_when_found():
    mock_repo.get_valid_access_token.return_value = "tok_abc123"
    result = await resolve_token(mock_repo, user_id=uuid4(), app_code="APP1")
    assert result == "tok_abc123"
```

---

### 5.12 `ebay/_idempotency.py` — Store Implementations

**`InMemoryIdempotencyStore`:**
- `get` on absent key returns None
- `set_if_absent` on new key returns True, stores value
- `set_if_absent` on existing key returns False, does not overwrite
- Thread safety: not tested in unit tests (that is a concurrency integration concern)

**`RedisIdempotencyStore`:**
- `get` with working client → returns decoded string value
- `get` when client raises → returns None (graceful degradation), logs warning
- `get` on bytes response → decoded to str
- `set_if_absent` with working client → returns True when NX succeeds, False when key exists
- `set_if_absent` when client raises → returns False, logs warning

**Singleton lifecycle (`get_idempotency_store` / `set_idempotency_store`):**
- `set_idempotency_store(InMemoryIdempotencyStore())` then `get_idempotency_store()` returns that instance
- `set_idempotency_store(None)` clears the singleton (next `get` rebuilds)
- Use `teardown` fixture to always reset to None after each singleton test

---

### 5.13 `ebay/listings_write_service.py` — Create, Update, End

Mock: `EbayAuthRepository`, `EbaySellingRepository`. Inject `InMemoryIdempotencyStore`
via `set_idempotency_store(...)`.

**`create_listing` scenarios:**
- Missing `idempotency_key` (empty string) → raises `ValueError`
- Idempotency cache hit with valid JSON → returns cached result without calling `selling_repository.create_listing`
- Idempotency cache hit with malformed JSON → falls through to actual API call (cache miss degradation)
- Cache miss: `resolve_token` returns token, API call succeeds, result stored in cache
- `resolve_token` raises (no token) → `ValueError` propagates
- Cache encode failure (`json.dumps` raises `TypeError`) → result still returned, warning logged; assert `selling_repository.create_listing` was called

**`end_listing` scenarios:**
- Missing `item_id` (empty string) → raises `ValueError`
- Happy path: token resolved, `selling_repository.delete_listing` called with correct payload

**`update_listing` scenarios:**
- Happy path: token resolved, `selling_repository.update_listing` called

---

### 5.14 `mtgjson/data_loader.py` — `_iter_card_rows`

This is the highest-value unit test target in the codebase. The function fans out
one raw MTGJson card dict into multiple staging row dicts. Bugs here silently corrupt
the price history table.

Read the function carefully before writing tests. Cover:

- Non-dict card entry → skipped (no rows emitted); assert generator is empty
- Card dict missing `paper` key → skipped
- Valid card with one source, one date, one price → emits one row with correct field mapping
- Source entry missing a currency key → that entry skipped, other entries still emitted
- Bad date string (non-parseable) → row skipped or emitted with None date (verify actual behavior)
- Bad price value (non-numeric string) → row skipped or emitted with None price (verify actual behavior)
- Card with multiple sources and multiple dates → emits one row per (source, date, currency) combination

Use `list(iter_card_rows(...))` to materialize the generator for each assertion.

---

### 5.15 `mtgjson/pipeline.py` — `check_version`

Mock: `MtgjsonRepository`.

- Version unchanged (repository returns same version string) → function returns early, no upsert called
- Version changed → upsert called with new version, result returned

---

### 5.16 `scryfall/data_loader.py` — Key Branches

**`download_cards_bulk`:**
- `uris_to_download` is empty list → returns immediately, no download called
- No URI in list matches `external_type` filter → returns with nothing downloaded
- One URI matches → download called for that URI only

**`delete_old_scryfall_folders`:**
- Empty folder list → no deletion called
- Three folders, `keep=2` → oldest folder deleted; newest two kept
- Folders with non-parseable date tokens → handled without crash

---

## 6. Fixtures and Scaffolding Design

### 6.1 Top-Level `conftest.py` (`tests/conftest.py`)

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_ops_repository():
    repo = AsyncMock()
    return repo

@pytest.fixture
def mock_session_repository():
    repo = AsyncMock()
    return repo

@pytest.fixture
def mock_user_repository():
    repo = AsyncMock()
    return repo

@pytest.fixture
def mock_auth_repository():
    repo = AsyncMock()
    return repo

@pytest.fixture
def mock_selling_repository():
    repo = AsyncMock()
    return repo
```

Each repository mock is an `AsyncMock()` so that `await repo.some_method()` works
without extra configuration. Add method-specific return values in the test body, not
in fixtures (keeps tests self-documenting).

### 6.2 Unit-Test `conftest.py` (`tests/unit/conftest.py`)

```python
import pytest
from automana.core.services.app_integration.ebay._idempotency import (
    set_idempotency_store,
    InMemoryIdempotencyStore,
)

@pytest.fixture(autouse=True)
def reset_idempotency_store():
    """Ensure singleton state does not leak between tests."""
    store = InMemoryIdempotencyStore()
    set_idempotency_store(store)
    yield store
    set_idempotency_store(None)
```

The `autouse=True` here is deliberate: forgetting to reset the singleton is a common
source of test-order-dependent flakiness.

### 6.3 JWT Test Helpers

```python
# tests/unit/api/services/auth/conftest.py
import pytest
from datetime import timedelta
from automana.api.services.auth.auth import create_access_token

TEST_SECRET = "test-secret-key-not-for-production"
TEST_ALGORITHM = "HS256"

@pytest.fixture
def valid_token():
    return create_access_token(
        data={"sub": "testuser", "user_id": "00000000-0000-0000-0000-000000000001"},
        secret_key=TEST_SECRET,
        algorithm=TEST_ALGORITHM,
        expires_delta=timedelta(hours=1),
    )

@pytest.fixture
def expired_token():
    return create_access_token(
        data={"sub": "testuser"},
        secret_key=TEST_SECRET,
        algorithm=TEST_ALGORITHM,
        expires_delta=timedelta(seconds=-1),
    )
```

### 6.4 Integrity Check Row Factories

```python
# tests/unit/core/services/ops/conftest.py
def make_check_row(severity: str, check_name: str = "test_check") -> dict:
    return {
        "check_name": check_name,
        "severity": severity,
        "row_count": 0 if severity == "ok" else 1,
        "details": f"{check_name} details",
    }
```

### 6.5 Settings Mock

`auth_service.py` and `session_service.py` call `get_general_settings()`. Avoid
importing real settings in unit tests. Use `mocker.patch`:

```python
@pytest.fixture
def mock_settings(mocker):
    settings = MagicMock()
    settings.jwt_secret_key = "test-jwt-key"
    settings.jwt_algorithm = "HS256"
    settings.secret_key = "test-secret"
    settings.encrypt_algorithm = "HS256"
    settings.access_token_expiry = "30"
    mocker.patch(
        "automana.api.services.auth.auth_service.get_general_settings",
        return_value=settings,
    )
    return settings
```

Patch at the **call site** (the module that imports `get_general_settings`), not at
the definition site. This is standard `unittest.mock` behaviour.

---

## 7. Phased Rollout

Tests are ordered by value-per-effort. Each phase is independently mergeable.

### Phase 1 — Tooling and Pure Logic — **SHIPPED**

All Phase 1 work items are complete and merged to main. Tests exist at:
- `tests/unit/api/services/auth/test_auth.py`
- `tests/unit/core/services/analytics/test_strategies.py`
- `tests/unit/core/services/analytics/test_utils.py`
- `tests/unit/core/services/ops/test_integrity_checks.py`

---

### Phase 2 — eBay Module and Ops Context Manager

**Goal:** Cover the eBay write-side services and the `track_step` context manager.

**Work items:**
1. Fix `auth_service.login` bug (see §8.1) — prerequisite for Phase 3, not Phase 2
2. `tests/unit/core/services/app_integration/ebay/test_auth_context.py`
3. `tests/unit/core/services/app_integration/ebay/test_idempotency.py`
4. `tests/unit/core/services/app_integration/ebay/test_listings_write_service.py`
5. `tests/unit/core/services/ops/test_pipeline_services.py`

---

### Phase 3 — Auth Services and Session Layer — **PARTIALLY SHIPPED**

Auth and session tests are complete and merged. User and role service tests are still pending.

**Shipped:**
- `tests/unit/api/services/auth/test_auth_service.py`
- `tests/unit/api/services/auth/test_session_service.py`

**Remaining work items:**
1. `tests/unit/api/services/user_management/test_user_service.py`
2. `tests/unit/api/services/user_management/test_role_service.py`

---

### Phase 4 — MTGJson and Scryfall ETL Services

**Goal:** Cover the data transformation logic that is most risky for silent corruption.

**Work items:**
1. `tests/unit/core/services/app_integration/mtgjson/test_data_loader.py` — focus on `_iter_card_rows`
2. `tests/unit/core/services/app_integration/mtgjson/test_pipeline.py` — `check_version`
3. `tests/unit/core/services/app_integration/scryfall/test_data_loader.py` — key branches

---

## 8. Known Bugs Blocking Tests

All bugs that were previously documented in this section have been fixed and merged to main. No active blockers remain.

---

## 9. What We Are Deliberately Not Testing

This section is as important as what we are testing. Every omission is intentional.

| What | Why not |
|------|---------|
| `analytics/reporting_services.py` | Single-line wrapper. If `analytics_repository.generate_daily_summary_report()` is mocked, the test asserts that Python function calls work. No value. |
| `card_catalog/*.py` (service layer) | These are thin delegation wrappers. The correctness risk is in the repository layer (SQL) and the router layer (schema validation). Unit tests here would only mock everything and confirm delegation. |
| `shopify/*.py` | Shopify API contracts are not stable enough to write meaningful unit assertions. The value is at integration layer with a Shopify sandbox. |
| `mtg_stock/data_staging.py` | `from_raw_to_staging` and `from_staging_to_prices` are two-line wrappers that update run status. The run-status logic is already covered by `track_step` tests. |
| Repository layer | Out of scope for this plan. Repository tests need a test DB fixture (TimescaleDB). That is a separate integration test effort. |
| Celery task chains | Celery `run_service.s(...)` wiring is integration territory. Unit tests mock `run_service` itself. |
| Router layer | Router tests require `TestClient` and full app startup. That is the `api` test marker scope. |
| `tools/tui/*` | TUI tooling is not the service layer. Not in scope. |
| Language features | We do not test that `list comprehensions work` or that `asyncio.gather runs coroutines`. |

---

## 10. Risks and Open Questions

### Risk 1 — Import-time side effects from `ServiceRegistry.register`

`@ServiceRegistry.register(...)` runs at import time. If the registry has global mutable
state, importing a service module in a test could register entries that persist across
tests and cause pollution. **Mitigation:** Read `ServiceRegistry` implementation before
writing the first test that imports a registered service. If the registry stores global
state, add a `reset_registry` fixture or ensure tests use isolated imports.

### Risk 2 — `get_general_settings()` pulls from real environment variables

`core/settings.py` uses `pydantic-settings` which reads `.env` and environment variables
at import time. A test run on a machine with a populated `.env` will pick up real secrets.
**Mitigation:** Mock `get_general_settings` at the call site in every service test.
Never let settings objects reach the test body uninstrumented.

### Risk 3 — `asyncio_mode = auto` interaction with existing code

If any existing test files (not yet present, but when added) mix sync and async fixtures,
`asyncio_mode = auto` can cause confusing errors. **Mitigation:** Establish the convention
that all fixtures in `tests/unit/` are sync unless they explicitly require async setup.
Async fixtures are only used when testing async context managers (like `track_step`).

### Risk 4 — `InMemoryIdempotencyStore` TTL behavior

The in-memory store does not enforce TTL. Tests that verify TTL expiry (e.g., "key
expires after 24h") cannot be unit tested without a fake clock. **Mitigation:** Do not
write TTL expiry tests at the unit level. Test TTL at the Redis integration layer using
`fakeredis`.

### Open Question 1 — `_iter_card_rows` error handling on bad dates/prices

The plan states "row skipped or emitted with None value — verify actual behavior." Before
writing those tests, read the current implementation carefully and assert the actual
behavior, not an assumed behavior. If the behavior is wrong (e.g., it raises instead of
skipping), that is a bug to fix before the test is written.

### Open Question 2 — `check_version` skip condition

The plan states the service "returns early" when the version is unchanged. Verify whether
"returns early" means returning `None`, returning a specific dict, or raising. The test
must assert the actual return value, not a vague "does not call upsert."

---

## 11. Consultations

### Sub-Agent Consultation Attempt

This plan was designed to include consultation with `senior-dev-reviewer` and
`python-sassy-architect` agent personas defined in `.claude/agents/`. However, the
invocation harness available in this session (claude-sonnet-4-6 via Claude Code) does
not provide the `Task` tool required to spawn sub-agents from persona files. The agent
files exist at `.claude/agents/senior-dev-reviewer.md` and `.claude/agents/python-sassy-architect.md`
but cannot be invoked programmatically from this context.

Rather than pretending a consultation occurred, the plan instead incorporates
self-review under each persona's declared perspective. This is noted transparently below.

### Self-Review in the Senior Dev Reviewer Persona

Concerns a senior engineer would raise on this plan:

1. **Phasing is realistic.** Phase 1 delivers working infrastructure and immediate
   coverage gains without touching broken code. That is the right call — don't block
   value on bug fixes.

2. **Bug documentation in §8 is necessary.** Papering over `auth_service.login` with
   fixture hacks would produce tests that pass on broken code. The plan correctly
   defers.

3. **Coverage targets are honest.** A single global 90% target is a vanity metric.
   Per-module tiering with explicit justifications for each tier is more defensible in
   code review.

4. **The `autouse=True` idempotency fixture is correct.** Singleton state leaking
   between tests is a real production issue — I have seen it cause order-dependent
   flakes that take hours to diagnose.

5. **One gap:** The plan does not specify what happens when `ServiceRegistry.register`
   is called at import time during tests. This should be investigated before Phase 1
   ships.

### Self-Review in the Python Sassy Architect Persona

Structural concerns from an architecture perspective:

1. **The `session_service.py` `print()` call (line 104) is a defect.** A service that
   uses `print()` instead of `logger.info()` is not production-grade. The test plan
   should note this as a cleanup item alongside the Bug section, not just silently
   work around it.

2. **`token_service.py` is not just buggy — it is architecturally incoherent.** Two
   definitions of the same function with different signatures suggests a failed merge
   or an incomplete refactor. Before writing any tests, the owner needs to decide what
   this service is supposed to do and rewrite it from scratch. Testing half-finished
   code is wasted effort.

3. **The `InMemoryIdempotencyStore` as a test double is excellent design.** It already
   exists in production code as a legitimate implementation. Using it in tests is not
   a hack — it is using the Strategy pattern as intended. This is the right approach
   and should be the model for how other external dependencies (Redis, Celery) are
   abstracted for testing.

4. **The `autouse` fixture for singleton reset should be in `tests/unit/conftest.py`,
   not a deeper conftest.** The idempotency store is a process-global singleton. Any
   unit test that imports `listings_write_service` can trigger it. The reset must be
   unconditional at the unit test level, not opt-in per subdirectory.

5. **`check_token_validity` takes a `Request` object.** The test will need
   `starlette.testclient.Request` or a `MagicMock` with a `.headers` attribute.
   Document this in the test file comment so the next developer does not spend twenty
   minutes figuring out why `request.headers.get()` fails on a plain `MagicMock`.
