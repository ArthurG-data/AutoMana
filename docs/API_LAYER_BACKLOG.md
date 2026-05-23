# API Layer — Bug & Technical Debt Backlog

Findings from a full senior-level review of `src/automana/api/` (2026-05-22).
Fixed items are marked ✅. Open items are ordered by priority.

---

## ✅ Fixed — 2026-05-22

| File | Issue |
|------|-------|
| `repositories/user_management/user_repository.py:174` | Missing `await` on `execute_command` — user deletion silently no-opped |
| `repositories/user_management/role_repository.py:55` | Swapped params `(user_id, role_name)` vs SQL `WHERE permission=$1 AND unique_id=$2` — every permission check returned false |
| `services/user_management/role_service.py:25` | `assign_role` passed wrong positional args to repo — `expires_at` landed in `reason`, `assigned_by` was silently dropped |
| `repositories/user_management/role_repository.py:28–29, 41` | SQL injection via f-string interpolation of `reason`/`assigned_by` into `SET LOCAL` — replaced with `set_config($1, true)` |

**Dead code removed:**
- `services/auth/cookie_utils.py` + entries in `core/framework/service_modules.py`
- `services/auth/token_service.py`
- `services/auth/get_hash_password.py`
- `repositories/auth/auth_repository.py`
- `request_handling/utils.py`
- `routers/auth.py` (0-byte stub)

---

## Open — High Priority

### H1 — `schemas/auth/token.py` — `check_expiry` validator always sets `is_expired = False`

`now < now + delta` is trivially true. Any code that reads `token.is_expired` will always see `False` regardless of actual expiry.

```python
# WRONG — current code
if datetime.now(timezone.utc) < datetime.now(timezone.utc) + timedelta(seconds=values.exp):
    values.is_expired = False

# FIX — compare against absolute expiry timestamp
if datetime.fromtimestamp(values.exp, tz=timezone.utc) > datetime.now(timezone.utc):
    values.is_expired = False
```

---

### H2 — `services/auth/auth_service.py:105` — service raises `HTTPException`

`login` raises `HTTPException(401)` directly inside the service. Services must not import or raise HTTP-layer exceptions — breaks Celery/internal callers and makes the service untestable without an HTTP context. The router's `if result is None` guard is unreachable dead code as a result.

**Fix:** Have `login` return `None` on bad credentials. The router's existing guard already handles this:
```python
# router already has this — just make login return None instead of raising
if result is None:
    raise HTTPException(status_code=401, detail="Invalid credentials")
```

---

### H3 — `services/auth/password_reset_service.py:65–69` — same architecture violation

`reset_password` raises `HTTPException(400)` for invalid/expired/used tokens inside the service layer.

**Fix:** Raise a domain exception (e.g. `InvalidResetTokenError`) and let the router translate it to 400.

---

### H4 — Four independent password-hashing implementations

| Location | Library |
|----------|---------|
| `services/auth/auth.py` | raw `bcrypt` |
| `utils/auth.py` | passlib `CryptContext(bcrypt)` |
| `core/utils/get_hash_password.py` | passlib `CryptContext(bcrypt)` |
| `worker/user_creation.py` | imports from `core.utils.auth` |

Hashes created by raw bcrypt and passlib bcrypt have slightly different formats. A hash created by one path may fail verification by another path silently. Designate `core/utils/get_hash_password.py` as canonical and remove the duplicates.

---

## Open — Medium Priority

### M1 — `dependancies/general.py:extract_ip` — AttributeError on UNIX sockets

`request.client.host` crashes when `request.client is None` (UNIX socket connections, some test environments).

```python
# FIX
return request.client.host if request.client else "unknown"
```

---

### M2 — eBay auth token cookie missing security flags

`routers/integrations/ebay/ebay_auth.py:230–234` — `httponly=True` and `secure=True` are commented out. The eBay OAuth token is accessible to JavaScript, creating an XSS exposure. Re-enable both flags; if a JS client needs to read the cookie, document that explicitly rather than silently commenting out the flags.

---

### M3 — `routers/integrations/ebay/scopes.py:30` — raw DB cursor in router

`regist_scope` injects a raw psycopg2 cursor directly into the router function, bypassing the ServiceManager. Architecture violation — register it with `ServiceRegistry` and call via `service_manager.execute_service(...)`.

---

### M4 — `routers/integrations/ebay/ebay_auth.py:13` — `get_settings()` called at import time

`settings = get_settings()` is module-level. If the module is imported before the environment is ready (e.g. test setup), it fails silently or uses stale defaults. Move `get_settings()` inside the functions that need it, or use the FastAPI dependency pattern established in `dependancies/service_deps.py`.

---

### M5 — `dependancies/query_deps.py` — `sort_params` default `sort_by="card_name"` leaks into non-card endpoints

`sort_params` is shared across session search and user search endpoints. Callers that omit `sort_by` silently sort by `card_name`, which is wrong for those endpoints. Either require callers to pass it explicitly or create `sort_params_users` / `sort_params_cards` variants.

---

### M6 — `utils/auth.py:24` — docstring says "argon2", scheme is bcrypt

```python
# FIX — update or remove the misleading docstring
```

---

## Open — Low Priority

### L1 — `user_repository.py` — `UserInDB(*user)` positional row unpacking

Two callsites in `services/user_management/user_service.py` unpack DB rows positionally. Adding or reordering a column will silently populate wrong fields.

```python
# FIX — unpack by name (asyncpg records support this)
UserInDB(**dict(user))
```

---

### L2 — `user_repository.py:16` — `add_many` uses psycopg2 `%s` placeholders

Every other method uses asyncpg `$N` placeholders. `add_many` uses `%s` and cannot execute through the asyncpg executor. Either delete it (if unused) or rewrite with asyncpg `executemany` and `$N` placeholders.

---

### L3 — `AsyncpgExceptionHandler` is stored but never called

`request_handling/ErrorHandler.py` defines a well-structured exception-to-HTTP mapping stored in `app.state.error_handler`. Every router has its own naked `except Exception: raise HTTPException(500)` instead of calling it. A thin decorator or middleware wrapper calling `app.state.error_handler.handle(e)` would eliminate all that copy-paste and give database errors correct HTTP codes automatically.

---

### L4 — Duplicated `_AUTH_ERRORS` / `_ERRORS` dicts across routers

Every router file defines its own inline `responses={}` dict for OpenAPI documentation. A shared `COMMON_RESPONSES` dict in `request_handling/` would eliminate the copy-paste and ensure consistent API documentation.
