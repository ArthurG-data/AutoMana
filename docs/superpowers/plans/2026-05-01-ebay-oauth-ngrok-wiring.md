# eBay OAuth VPS Tunnel Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing eBay OAuth flow through the VPS tunnel by fixing nginx auth bypass for the callback, widening the `redirect_uri` column, and adding a PATCH endpoint to update the stored redirect URI.

**Architecture:** Three-layer change — nginx config unblocks eBay's redirect, a DB migration widens the column to fit the full URL, and a new PATCH endpoint + service + repository method lets the admin update `app_info.redirect_uri` without re-registering the whole app.

**Tech Stack:** nginx, PostgreSQL, FastAPI, asyncpg, pytest

---

## Files

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/automana/database/SQL/migrations/migration_19_widen_redirect_uri.sql` | Widen `redirect_uri` to VARCHAR(255) |
| Modify | `deploy/docker/nginx/nginx.local.conf` | Add `auth_basic off` for callback path |
| Modify | `src/automana/core/repositories/app_integration/ebay/app_queries.py` | Add `update_redirect_uri_query` |
| Modify | `src/automana/core/repositories/app_integration/ebay/app_repository.py` | Add `update_redirect_uri` method |
| Modify | `src/automana/core/services/app_integration/ebay/auth_services.py` | Register `integrations.ebay.update_app_redirect_uri` |
| Modify | `src/automana/api/routers/integrations/ebay/ebay_auth.py` | Add `PATCH /admin/apps/{app_code}/redirect-uri` |
| Create | `tests/unit/core/repositories/app_integration/ebay/__init__.py` | Package marker |
| Create | `tests/unit/core/repositories/app_integration/ebay/test_app_repository.py` | Unit tests for `update_redirect_uri` |

---

## Task 1: DB Migration — Widen redirect_uri Column

`redirect_uri VARCHAR(50)` is too short for the full tunnel callback URL (72 chars). This migration widens it to VARCHAR(255).

**Files:**
- Create: `src/automana/database/SQL/migrations/migration_19_widen_redirect_uri.sql`

- [ ] **Step 1: Write the migration file**

```sql
-- migration_19_widen_redirect_uri.sql
-- Widens app_info.redirect_uri from VARCHAR(50) to VARCHAR(255)
-- so full VPS tunnel/production URLs fit without truncation.
ALTER TABLE app_integration.app_info
    ALTER COLUMN redirect_uri TYPE VARCHAR(255);
```

- [ ] **Step 2: Also fix the schema file to match (idempotent for future rebuilds)**

In `src/automana/database/SQL/schemas/05_ebay.sql`, change line 10:

```sql
-- before
    redirect_uri VARCHAR(50) NOT NULL,
-- after
    redirect_uri VARCHAR(255) NOT NULL,
```

- [ ] **Step 3: Apply the migration to the dev DB**

```bash
docker exec -i automana-postgres-dev psql -U app_admin -d automana_dev \
  < src/automana/database/SQL/migrations/migration_19_widen_redirect_uri.sql
```

Expected output:
```
ALTER TABLE
```

- [ ] **Step 4: Verify the column width**

```bash
docker exec -i automana-postgres-dev psql -U app_admin -d automana_dev -c \
  "\d app_integration.app_info" | grep redirect_uri
```

Expected: `redirect_uri | character varying(255) | not null`

- [ ] **Step 5: Commit**

```bash
git add src/automana/database/SQL/migrations/migration_19_widen_redirect_uri.sql \
        src/automana/database/SQL/schemas/05_ebay.sql
git commit -m "feat(db): migration 19 — widen app_info.redirect_uri to VARCHAR(255)"
```

---

## Task 2: nginx — Bypass auth_basic for eBay Callback

eBay's OAuth redirect doesn't send Basic Auth credentials, so the port-8080 server block returns 401. Add a dedicated location block that disables auth for exactly this path.

**Files:**
- Modify: `deploy/docker/nginx/nginx.local.conf`

- [ ] **Step 1: Add the callback location block in the port-8080 server block**

In `deploy/docker/nginx/nginx.local.conf`, inside the `server { listen 8080; ... }` block, add this block **before** the `location /api/ {` block:

```nginx
        location = /api/integrations/ebay/auth/callback {
            auth_basic off;
            proxy_pass         http://fastapi_backend;
            proxy_http_version 1.1;
            proxy_connect_timeout 60s;
            proxy_send_timeout    60s;
            proxy_read_timeout    60s;
        }
```

The `=` modifier does exact-match only — no other paths are affected.

- [ ] **Step 2: Reload nginx**

```bash
docker exec automana-nginx-dev nginx -t && \
docker exec automana-nginx-dev nginx -s reload
```

Expected:
```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

- [ ] **Step 3: Smoke-test the callback path reaches FastAPI without auth**

```bash
curl -s -o /dev/null -w "%{http_code}" \
  http://localhost:8080/api/integrations/ebay/auth/callback
```

Expected: `400` (FastAPI rejects missing `code`/`state` params — not `401`, which would mean nginx still blocked it).

- [ ] **Step 4: Commit**

```bash
git add deploy/docker/nginx/nginx.local.conf
git commit -m "fix(nginx): bypass auth_basic for eBay OAuth callback on port 8080"
```

---

## Task 3: Repository — Add update_redirect_uri

Add the query constant and the async method. No service layer touched yet — the service in Task 4 depends on this.

**Files:**
- Modify: `src/automana/core/repositories/app_integration/ebay/app_queries.py`
- Modify: `src/automana/core/repositories/app_integration/ebay/app_repository.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/core/repositories/app_integration/ebay/__init__.py` (empty).

Create `tests/unit/core/repositories/app_integration/ebay/test_app_repository.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from automana.core.repositories.app_integration.ebay.app_repository import EbayAppRepository


@pytest.fixture
def repo():
    conn = MagicMock()
    executor = MagicMock()
    r = EbayAppRepository(connection=conn, executor=executor)
    r.execute_query = AsyncMock()
    return r


@pytest.mark.asyncio
async def test_update_redirect_uri_returns_true_on_success(repo):
    repo.execute_query.return_value = [{"app_code": "my-app"}]
    result = await repo.update_redirect_uri("my-app", "https://automana.duckdns.org/api/integrations/ebay/auth/callback")
    assert result is True


@pytest.mark.asyncio
async def test_update_redirect_uri_returns_false_when_app_not_found(repo):
    repo.execute_query.return_value = []
    result = await repo.update_redirect_uri("unknown-app", "https://automana.duckdns.org/api/integrations/ebay/auth/callback")
    assert result is False


@pytest.mark.asyncio
async def test_update_redirect_uri_passes_correct_args(repo):
    repo.execute_query.return_value = [{"app_code": "my-app"}]
    url = "https://automana.duckdns.org/api/integrations/ebay/auth/callback"
    await repo.update_redirect_uri("my-app", url)
    repo.execute_query.assert_called_once()
    call_args = repo.execute_query.call_args
    assert call_args[0][1] == (url, "my-app")
```

- [ ] **Step 2: Run the tests — expect ImportError or AttributeError**

```bash
pytest tests/unit/core/repositories/app_integration/ebay/test_app_repository.py -v
```

Expected: FAIL (`update_redirect_uri` not defined yet).

- [ ] **Step 3: Add the query constant to app_queries.py**

Append to `src/automana/core/repositories/app_integration/ebay/app_queries.py`:

```python
update_redirect_uri_query = """
UPDATE app_integration.app_info
SET redirect_uri = $1,
    updated_at   = now()
WHERE app_code = $2
RETURNING app_code;
"""
```

- [ ] **Step 4: Add the repository method to app_repository.py**

In `src/automana/core/repositories/app_integration/ebay/app_repository.py`, replace the stub `def update(self, values):` with a real implementation and add the new async method. Add the import for `app_queries` at the top if not already present (it is already imported as `from automana.core.repositories.app_integration.ebay import app_queries`).

Add this method to the `EbayAppRepository` class (before the `list` method):

```python
    async def update_redirect_uri(self, app_code: str, redirect_uri: str) -> bool:
        result = await self.execute_query(
            app_queries.update_redirect_uri_query,
            (redirect_uri, app_code)
        )
        return bool(result)
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
pytest tests/unit/core/repositories/app_integration/ebay/test_app_repository.py -v
```

Expected: 3 PASSED.

- [ ] **Step 6: Commit**

```bash
git add tests/unit/core/repositories/app_integration/ebay/__init__.py \
        tests/unit/core/repositories/app_integration/ebay/test_app_repository.py \
        src/automana/core/repositories/app_integration/ebay/app_queries.py \
        src/automana/core/repositories/app_integration/ebay/app_repository.py
git commit -m "feat(ebay): add update_redirect_uri query and repository method"
```

---

## Task 4: Service — Register update_app_redirect_uri

Register a new service that wires the repository method into the `ServiceRegistry`, following the same pattern as `register_app` in `auth_services.py`.

**Files:**
- Modify: `src/automana/core/services/app_integration/ebay/auth_services.py`

- [ ] **Step 1: Add the service function at the bottom of auth_services.py**

Append to `src/automana/core/services/app_integration/ebay/auth_services.py`:

```python
@ServiceRegistry.register(
    'integrations.ebay.update_app_redirect_uri',
    db_repositories=['app']
)
async def update_app_redirect_uri(
    app_repository: EbayAppRepository,
    app_code: str,
    redirect_uri: str,
) -> bool:
    """Update the redirect_uri stored for an eBay app."""
    updated = await app_repository.update_redirect_uri(app_code, redirect_uri)
    if not updated:
        raise app_exception.EbayAppNotFoundException(
            f"eBay app with code {app_code!r} not found"
        )
    return updated
```

Note: `EbayAppRepository` is already imported at the top of the file via `from automana.core.repositories.app_integration.ebay.app_repository import EbayAppRepository`. Verify it is — if not, add the import.

- [ ] **Step 2: Verify the import is present**

```bash
grep "EbayAppRepository" src/automana/core/services/app_integration/ebay/auth_services.py
```

Expected: at least one line showing the import. If absent, add:
```python
from automana.core.repositories.app_integration.ebay.app_repository import EbayAppRepository
```

- [ ] **Step 3: Smoke-test the registration loads without error**

```bash
python -c "
from automana.core.services.app_integration.ebay.auth_services import update_app_redirect_uri
from automana.core.service_registry import ServiceRegistry
assert 'integrations.ebay.update_app_redirect_uri' in ServiceRegistry._registry
print('OK')
"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/automana/core/services/app_integration/ebay/auth_services.py
git commit -m "feat(ebay): register update_app_redirect_uri service"
```

---

## Task 5: Router — Add PATCH /admin/apps/{app_code}/redirect-uri

Admin-only endpoint that calls the new service. Follows the pattern of the existing `POST /admin/apps` endpoint.

**Files:**
- Modify: `src/automana/api/routers/integrations/ebay/ebay_auth.py`

- [ ] **Step 1: Add a request model for the PATCH body**

At the top of `src/automana/api/routers/integrations/ebay/ebay_auth.py`, add this import (Pydantic is already available via FastAPI):

The existing import line is:
```python
from automana.core.models.ebay.auth import AppRegistrationRequest, CreateAppRequest
```

Change it to:
```python
from automana.core.models.ebay.auth import AppRegistrationRequest, CreateAppRequest
from pydantic import BaseModel, HttpUrl
```

Then add the request model after the imports and before the router definition:

```python
class UpdateRedirectUriRequest(BaseModel):
    redirect_uri: str
```

- [ ] **Step 2: Add the PATCH endpoint**

Append to `src/automana/api/routers/integrations/ebay/ebay_auth.py` (before the `from automana.api.schemas.auth.cookie import ...` import at the bottom):

```python
@ebay_auth_router.patch(
    '/admin/apps/{app_code}/redirect-uri',
    description='Update the redirect URI for a registered eBay app',
    status_code=status.HTTP_200_OK,
)
async def update_redirect_uri(
    app_code: str,
    body: UpdateRedirectUriRequest,
    user: CurrentUserDep,
    service_manager: ServiceManagerDep,
):
    try:
        await service_manager.execute_service(
            "integrations.ebay.update_app_redirect_uri",
            app_code=app_code,
            redirect_uri=body.redirect_uri,
        )
        return ApiResponse(
            message="Redirect URI updated successfully",
            data={
                "app_code": app_code,
                "redirect_uri": body.redirect_uri,
            },
        )
    except Exception:
        raise
```

- [ ] **Step 3: Verify the app starts cleanly**

```bash
docker exec automana-backend-dev python -c \
  "from automana.api.main import app; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Hit the endpoint via curl to verify routing (needs running stack)**

```bash
# Get a token first (replace TOKEN with a valid JWT)
curl -s -X PATCH \
  "http://localhost:8000/api/integrations/ebay/auth/admin/apps/YOUR_APP_CODE/redirect-uri" \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"redirect_uri": "https://automana.duckdns.org/api/integrations/ebay/auth/callback"}' \
  | python3 -m json.tool
```

Expected: `200` response with `"redirect_uri"` in the data field.

- [ ] **Step 5: Commit**

```bash
git add src/automana/api/routers/integrations/ebay/ebay_auth.py
git commit -m "feat(ebay): PATCH /admin/apps/{app_code}/redirect-uri endpoint"
```

---

## Task 6: End-to-End OAuth Flow Verification

Manual steps to confirm the full flow works through the VPS tunnel. No code changes.

- [ ] **Step 1: Confirm the VPS tunnel is live**

```bash
curl -s https://automana.duckdns.org/health | python3 -m json.tool
```

Expected: `{"status": "ok"}` (or similar health response — no auth prompt, no 502).

- [ ] **Step 2: Update redirect_uri in the DB via the PATCH endpoint**

```bash
curl -s -X PATCH \
  "https://automana.duckdns.org/api/integrations/ebay/auth/admin/apps/YOUR_APP_CODE/redirect-uri" \
  -u "dev:automana-dev" \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"redirect_uri": "https://automana.duckdns.org/api/integrations/ebay/auth/callback"}'
```

Expected: `200` with updated redirect_uri.

- [ ] **Step 3: Start the OAuth flow**

```bash
curl -s -X POST \
  "https://automana.duckdns.org/api/integrations/ebay/auth/app/login?app_code=YOUR_APP_CODE" \
  -u "dev:automana-dev" \
  -H "Authorization: Bearer TOKEN" \
  | python3 -m json.tool
```

Expected: JSON with `"authorization_url"` pointing to `auth.sandbox.ebay.com` (or `auth.ebay.com` for production).

- [ ] **Step 4: Open the authorization_url in a browser**

Visit the URL from Step 3. Log in with your eBay sandbox/production credentials and approve. eBay will redirect to:
```
https://automana.duckdns.org/api/integrations/ebay/auth/callback?code=...&state=...
```

Expected: Response from FastAPI with `{"message": "eBay authorization successful", ...}`.

- [ ] **Step 5: Exchange the refresh token for an access token**

```bash
curl -s -X POST \
  "https://automana.duckdns.org/api/integrations/ebay/auth/exange_token?app_code=YOUR_APP_CODE" \
  -u "dev:automana-dev" \
  -H "Authorization: Bearer TOKEN" \
  | python3 -m json.tool
```

Expected: `200` with `"cookie_set": true` and `"expires_in"` value.
