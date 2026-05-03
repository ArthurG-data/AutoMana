# Backend Testing Strategy

This document describes the testing pyramid, patterns, fixtures, and best practices used in AutoMana.

---

## Testing Pyramid

AutoMana follows the testing pyramid recommended in the industry:

- **Unit Tests (40%)**: Fast, isolated, no external dependencies
- **Integration Tests (50%)**: Real database, Redis, and schema; tests of services and repositories
- **E2E Tests (10%)**: Full stack including HTTP routing and authentication

```
        /\
       /  \  E2E Tests (10%)
      /    \
     /______\
    /        \
   / Integration (50%)
  /____________\
 /              \
/   Unit (40%)   \
/________________\
```

### Running Tests by Category

```bash
# Unit tests only (fastest, default)
pytest tests/unit

# Integration tests (requires Docker, ~30s per test)
pytest tests/integration

# All tests
pytest

# All except slow tests
pytest -m "not slow"

# Specific marker
pytest -m "service"        # service-layer tests only
pytest -m "repository"     # repository-layer tests only
pytest -m "pipeline"       # Celery pipeline tests
pytest -m "api"            # full-stack API tests
```

See `pytest.ini` for marker definitions and defaults.

---

## Unit Testing

Unit tests are isolated, fast, and use mocked dependencies.

### Where unit tests live

```
tests/unit/
├── core/
│   ├── metrics/
│   │   └── test_registry.py
│   └── conftest.py
├── api/
│   ├── services/
│   │   ├── auth/
│   │   │   ├── test_auth_service.py
│   │   │   ├── test_session_service.py
│   │   │   └── test_auth.py
│   │   └── conftest.py
│   └── routers/
│       └── ...
└── worker/
    ├── test_mtgstock_pipeline_wiring.py
    └── conftest.py
```

### Unit Test Structure

Unit tests must NOT touch the database or external services. Use `AsyncMock` for all repositories and services.

**Example: testing auth service with mocked repositories**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from automana.api.services.auth.auth_service import login
from automana.api.schemas.user_management.user import UserInDB

pytestmark = pytest.mark.unit

def _make_user(username: str = "alice") -> MagicMock:
    user = MagicMock(spec=UserInDB)
    user.unique_id = uuid4()
    user.username = username
    return user

class TestLogin:
    async def test_login_returns_access_token(self, monkeypatch, mock_session_repository, mock_user_repository):
        """Verify login creates a session and returns a valid JWT."""
        known_uuid = uuid4()
        known_token = "actual-refresh-token-value"

        # Mock the settings
        monkeypatch.setattr(
            "automana.api.services.auth.auth_service.get_general_settings",
            lambda: _StrictSettings(jwt_secret_key="test-secret", access_token_expiry=30),
        )
        
        # Mock external service calls
        monkeypatch.setattr(
            "automana.api.services.auth.auth_service.create_new_session",
            AsyncMock(return_value={"session_id": known_uuid, "refresh_token": known_token}),
        )
        monkeypatch.setattr(
            "automana.api.services.auth.auth_service.authenticate_user",
            AsyncMock(return_value=_make_user()),
        )
        mock_session_repository.get_by_user_id = AsyncMock(return_value=[])

        result = await login(
            user_repository=mock_user_repository,
            session_repository=mock_session_repository,
            username="alice",
            password="testpass",
            ip_address="127.0.0.1",
            user_agent="pytest",
        )

        assert result.get("session_id") == str(known_uuid)
        assert result.get("refresh_token") == known_token
        assert "access_token" in result
```

### Fixtures

Unit tests use shared fixtures defined in `tests/conftest.py` and `tests/unit/conftest.py`.

**Global fixtures** (`tests/conftest.py`):
- `mock_ops_repository` — `AsyncMock()` for ops queries
- `mock_session_repository` — `AsyncMock()` for session storage
- `mock_user_repository` — `AsyncMock()` for user queries
- `mock_auth_repository` — `AsyncMock()` for auth operations
- `mock_selling_repository` — `AsyncMock()` for eBay/Shopify data

**Unit-specific fixtures** (`tests/unit/conftest.py`):
- `reset_idempotency_store` — auto-use fixture that resets the eBay idempotency singleton before and after every unit test, preventing state leaks across tests

### Mocking Strategies

#### 1. Mock Return Values

```python
mock_user_repo.get_by_id = AsyncMock(return_value=user_obj)
result = await my_service(user_repo=mock_user_repo)
assert result == expected
```

#### 2. Mock Side Effects (Multiple Calls)

```python
mock_user_repo.list_all = AsyncMock(
    side_effect=[
        [user1, user2],  # first call
        [],              # second call
    ]
)
```

#### 3. Verify Calls

```python
await my_service(user_repo=mock_user_repo)
mock_user_repo.get_by_id.assert_called_once_with(user_id=123)
```

#### 4. Mock Exceptions

```python
from automana.core.exceptions import ResourceNotFoundError

mock_user_repo.get_by_id = AsyncMock(
    side_effect=ResourceNotFoundError(resource="User", identifier="123")
)
```

---

## Integration Testing

Integration tests use real PostgreSQL (+ TimescaleDB), real Redis, and real database schema.

### Where integration tests live

```
tests/integration/
├── api/
│   ├── test_health.py
│   ├── auth/
│   │   ├── test_login.py
│   │   └── test_token_refresh.py
│   └── catalog/
│       └── ...
├── services/
│   ├── mtgjson/
│   │   ├── test_promote_staging.py
│   │   └── conftest.py
│   ├── scryfall/
│   │   └── ...
│   └── conftest.py
└── repositories/
    ├── user/
    │   └── test_user_repository.py
    └── conftest.py
```

### Integration Test Scaffolding

Integration tests depend on session-scoped fixtures that start Docker containers:

**`tests/integration/conftest.py` responsibilities:**
1. Starts TimescaleDB + pgvector container
2. Starts Redis container
3. Overrides `POSTGRES_HOST`, `POSTGRES_PORT`, `REDIS_HOST`, `REDIS_PORT` in environment before importing automana
4. Clears the `get_settings()` lru_cache and purges automana modules from `sys.modules` so fresh imports read the new env vars
5. Runs all SQL schema and migration files against the fresh database
6. Provides an async httpx client with FastAPI lifespan running

**Key fixtures:**
- `timescale_container` — session-scoped TimescaleDB container
- `redis_container` — session-scoped Redis container
- `_test_env` — session-scoped env override (must run before automana is imported)
- `db_migrations_applied` — session-scoped SQL migration runner
- `test_app` — session-scoped FastAPI app with lifespan
- `client` — session-scoped async httpx client

### Health Check (Canary Test)

The health check test is the smoke test for the entire test scaffolding:

```python
# tests/integration/api/test_health.py
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.api]

async def test_health_endpoint_returns_200(client):
    """Smoke test: proves containers, env override, migrations, and lifespan work."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
```

If this test fails, the scaffolding is broken. If it passes, you know:
1. Containers started successfully
2. Environment variables are primed correctly
3. Migrations applied cleanly
4. FastAPI lifespan initialized without errors
5. httpx/ASGI transport is correctly wired

### Database Seeding and Cleanup

Integration tests often need to seed the database with reference rows. Use fixtures with yield to clean up after:

```python
@pytest_asyncio.fixture
async def seeded_db(db_pool):
    """Seed reference rows; clean up after."""
    async with db_pool.acquire() as conn:
        # INSERT reference rows (cards, sets, rarities, etc.)
        set_id = await conn.fetchval(
            "INSERT INTO card_catalog.sets (set_name, set_code, ...) VALUES (...) RETURNING set_id"
        )
        card_id = await conn.fetchval(
            "INSERT INTO card_catalog.unique_cards_ref (card_name) VALUES (...) RETURNING unique_card_id"
        )
    
    yield {"set_id": set_id, "card_id": card_id}
    
    # CLEANUP: DELETE the seeded rows
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM card_catalog.sets WHERE set_id = $1", set_id)
```

### Database Pool Access

To interact with the database in integration tests, request the `db_pool` fixture:

```python
@pytest_asyncio.fixture
async def test_my_repo(db_pool):
    """Test the card repository against real schema."""
    repo = CardRepository(db_pool)
    yield repo
    # cleanup if needed
```

### Example: Full-Stack API Test

```python
# tests/integration/api/catalog/test_create_collection.py
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.api]

async def test_create_collection_requires_auth(client):
    """Unauthenticated requests should be rejected."""
    response = await client.post(
        "/api/catalog/mtg/collection/",
        json={"collection_name": "My Cards", "description": "..."}
    )
    assert response.status_code == 401

async def test_create_collection_succeeds_with_auth(client, authenticated_user):
    """Authenticated user can create a collection."""
    token = authenticated_user["access_token"]
    response = await client.post(
        "/api/catalog/mtg/collection/",
        headers={"Authorization": f"Bearer {token}"},
        json={"collection_name": "My Cards", "description": "Test collection"}
    )
    assert response.status_code == 201
    assert response.json()["data"]["collection_name"] == "My Cards"
```

---

## E2E Testing

E2E tests cover the full user journey and are described in [`docs/backend/testing/API_TESTING.md`](API_TESTING.md).

For automated E2E, write integration tests with the full API stack and auth flow. For manual E2E, use the testing flow documented in API_TESTING.md.

---

## Factories and Test Data

Use factory functions to create test data consistently:

```python
from uuid import uuid4
from datetime import datetime

def make_user(username: str = "testuser", email: str = None) -> dict:
    """Factory: return a user dict for database insertion."""
    return {
        "unique_id": str(uuid4()),
        "username": username,
        "email": email or f"{username}@example.com",
        "hashed_password": "bcrypted_password_hash_here",
        "created_at": datetime.utcnow(),
    }

def make_card_entry(
    card_version_id: str = None,
    condition: str = "NM",
    finish: str = "NONFOIL",
    purchase_price: float = 10.00,
) -> dict:
    """Factory: return a card entry dict for insertion."""
    return {
        "card_version_id": card_version_id or str(uuid4()),
        "condition": condition,
        "finish": finish,
        "purchase_price": purchase_price,
        "added_at": datetime.utcnow(),
    }

# Usage in a test
async def test_add_card_to_collection(db_pool, authenticated_user):
    user_data = make_user(username="alice")
    entry_data = make_card_entry(condition="LP", purchase_price=15.50)
    # ... insert and assert
```

---

## Coverage Targets

The project aims for:
- **Unit tests**: 80%+ coverage of service logic, utilities, and schemas
- **Integration tests**: 60%+ coverage of repositories and API routes
- **Overall**: 70%+ combined coverage

Run coverage reports:

```bash
# With coverage report
pytest --cov=automana --cov-report=html tests/

# Open the HTML report
open htmlcov/index.html
```

---

## Common Patterns

### Asserting Async Mock Calls

```python
# Was called once?
mock_repo.save.assert_called_once()

# Was called with specific args?
mock_repo.save.assert_called_once_with(user_id=123, data={"name": "Alice"})

# How many times was it called?
assert mock_repo.save.call_count == 3

# What arguments were passed on each call?
calls = mock_repo.save.call_args_list
assert calls[0][1]["user_id"] == 123  # first call, kwargs
```

### Testing Error Handling

```python
from automana.core.exceptions import ResourceNotFoundError

async def test_get_nonexistent_user_raises(mock_user_repo):
    """Service should raise ResourceNotFoundError for missing users."""
    mock_user_repo.get_by_id = AsyncMock(
        side_effect=ResourceNotFoundError(resource="User", identifier="999")
    )
    
    with pytest.raises(ResourceNotFoundError):
        await my_service(user_repo=mock_user_repo, user_id="999")
```

### Testing Service with Transaction

Services that use transactions often depend on a repository fixture. Mock the transaction context:

```python
async def test_service_with_transaction(mock_user_repo):
    """Service opens a transaction and rolls back on error."""
    mock_user_repo.acquire_transaction = AsyncMock()
    mock_transaction = AsyncMock()
    mock_user_repo.acquire_transaction.return_value.__aenter__.return_value = mock_transaction
    
    # ... call service, assert transaction was acquired
```

---

## CI/CD Test Integration

Tests are run in CI using GitHub Actions (see `.github/workflows/test.yml`):

1. **Lint phase**: Runs `flake8`, `black`, and type checking
2. **Unit test phase**: Runs `pytest tests/unit/` (fast, no Docker required)
3. **Integration test phase**: Runs `pytest tests/integration/` (spawns containers, ~5min)
4. **Coverage phase**: Reports coverage to Codecov

All phases must pass before merging to `main`.

Local pre-commit hook (if configured) runs unit tests before allowing `git commit`.

---

## Best Practices

1. **Keep unit tests isolated**: No database, no HTTP, no Redis. Use `AsyncMock` for all dependencies.

2. **Name tests clearly**: Use `test_<what_is_being_tested>_<expected_outcome>` format.
   - ✅ `test_login_with_invalid_password_raises_auth_error`
   - ❌ `test_login_bad_pass`

3. **Use the testing pyramid**: Aim for many fast unit tests, fewer integration tests, minimal E2E tests.

4. **Seed reference data, not test data**: Tests should create only the data they need. Use factories to keep setup DRY.

5. **Clean up after yourself**: Use fixture cleanup (yield) to delete seeded rows or reset state.

6. **Test error paths**: Not just happy paths. Test invalid inputs, missing resources, permission errors.

7. **Use markers liberally**: Mark tests with `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`, etc.

8. **Avoid sleeps in tests**: Use `pytest.wait_for()` or fixture-based polling for async operations.

9. **Mock at boundaries**: Mock external services, filesystem, and HTTP. Test business logic with real data structures.

10. **Document complex test setup**: If a test fixture is non-obvious, add a docstring explaining what it does.

---

## See Also

- [`docs/backend/testing/API_TESTING.md`](API_TESTING.md) — Manual API testing with curl/Postman
- [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) — Layered architecture and request flow
- [`docs/DESIGN_PATTERNS.md`](../DESIGN_PATTERNS.md) — Service registry, dependency injection, context object
- `pytest.ini` — Pytest configuration (test paths, markers, asyncio mode)
- `tests/conftest.py` — Top-level shared fixtures
