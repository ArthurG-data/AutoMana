
# AutoMana API

This document is a human-friendly reference for the FastAPI endpoints.

For the authoritative, always-up-to-date spec, use:

- Swagger UI: `GET /docs`
- OpenAPI JSON: `GET /openapi.json`

## Base URLs

- Local dev (typical): `http://localhost:8000`
- Production: whatever your reverse proxy exposes (only the `proxy` container should publish ports).

All application routes live under:

- API prefix: `/api`

## Health & Root

- `GET /` → basic welcome payload + docs path
- `GET /health` → `{ "status": "healthy" }`

## Authentication (session cookie)

Most “user” endpoints rely on a **session cookie** named `session_id`.

### Login

- `POST /api/users/auth/token`
	- Body: `application/x-www-form-urlencoded` (OAuth2PasswordRequestForm)
		- `username`
		- `password`
	- Returns a JSON token payload (including `access_token`) and sets a `session_id` cookie (`httponly`, `secure` outside dev, `samesite=strict`). The `access_token` is in the JSON body only — no cookie is set for it.

Example (curl):

```bash
# Login and store cookies in a file
curl -i -c cookies.txt \
	-X POST "http://localhost:8000/api/users/auth/token" \
	-H "Content-Type: application/x-www-form-urlencoded" \
	-d "username=YOUR_USERNAME&password=YOUR_PASSWORD"

# Call an authenticated endpoint using the stored session cookie
curl -b cookies.txt "http://localhost:8000/api/users/users/me"
```

### Logout

- `POST /api/users/auth/logout` → clears `session_id` cookie

### Refresh

- `POST /api/users/auth/token/refresh`
	- Exchanges the refresh token in cookie for a new auth token.

## Response envelopes

Many endpoints return a standard shape defined in [`src/automana/api/schemas/StandardisedQueryResponse.py`](../src/automana/api/schemas/StandardisedQueryResponse.py).

### `ApiResponse`

```json
{
	"success": true,
	"status": "success",
	"message": "...",
	"data": {},
	"timestamp": "...",
	"request_id": "..."
}
```

### `PaginatedResponse`

```json
{
	"success": true,
	"status": "success",
	"data": [],
	"pagination": {
		"limit": 10,
		"offset": 0,
		"total_count": 123,
		"has_next": true,
		"has_previous": false
	}
}
```

### Errors

FastAPI errors commonly follow:

```json
{ "detail": "..." }
```

Some modules also define an `ErrorResponse` model.

## Common query conventions

Some list/search endpoints use shared dependency helpers and tend to accept:

- Pagination: `limit`, `offset`
- Sorting: `sort_by`, `sort_order`
- Date ranges (varies by endpoint): `created_after`, `created_before` / `released_after`, `released_before`

## Endpoints (by area)

### Users

Auth (`/api/users/auth`)

- `POST /api/users/auth/token` — login; sets `session_id` cookie (httponly); returns `access_token` in JSON body for Bearer use
- `POST /api/users/auth/token/refresh` — refresh access token
- `POST /api/users/auth/logout` — logout (clears cookie)

Sessions (`/api/users/session`)

- `GET /api/users/session/{session_id}` — get one session
- `GET /api/users/session/` — search sessions (paginated)
- `DELETE /api/users/session/{session_id}/deactivate` — deactivate a session

Users (`/api/users/users`)

- `GET /api/users/users/me` — current user (requires `session_id` cookie)
- `GET /api/users/users/` — search users (paginated)
- `POST /api/users/users/` — register/add a user
- `PUT /api/users/users/` — update current user
- `DELETE /api/users/users/{user_id}` — delete a user
- `POST /api/users/users/{user_id}/roles` — assign role
- `DELETE /api/users/users/{user_id}/roles/{role_name}` — revoke role

### Catalog

Base: `/api/catalog/mtg`

Card reference (`/api/catalog/mtg/card-reference`)

- `GET /api/catalog/mtg/card-reference/suggest` — autocomplete card names (typo-tolerant, fuzzy matching via pg_trgm; `q` min 2 chars, `limit` 1-20; cached 10 min)
- `GET /api/catalog/mtg/card-reference/{card_id}` — get card by id
- `GET /api/catalog/mtg/card-reference/` — search cards (paginated; supports `name`, `oracle_text`, `format`, plus other filters; cached 60 min)
- `POST /api/catalog/mtg/card-reference/` — insert a card
- `POST /api/catalog/mtg/card-reference/bulk` — insert up to 50 cards
- `POST /api/catalog/mtg/card-reference/upload-file` — upload large JSON file
- `DELETE /api/catalog/mtg/card-reference/{card_id}` — delete card

Collections (`/api/catalog/mtg/collection`)

- `POST /api/catalog/mtg/collection/` — create collection (requires `session_id`)
- `GET /api/catalog/mtg/collection/{collection_id}` — get one collection (requires `session_id`)
- `GET /api/catalog/mtg/collection/` — list collections (requires `session_id`)
- `PUT /api/catalog/mtg/collection/{collection_id}` — update collection (requires `session_id`)
- `DELETE /api/catalog/mtg/collection/{collection_id}` — delete collection (requires `session_id`)

Note: there are “entry” endpoints marked as TODO/incomplete in code; they may change.

Set reference (`/api/catalog/mtg/set-reference`)

- `GET /api/catalog/mtg/set-reference/{set_id}`
- `GET /api/catalog/mtg/set-reference/` (paginated)
- `POST /api/catalog/mtg/set-reference/`
- `POST /api/catalog/mtg/set-reference/bulk`
- `POST /api/catalog/mtg/set-reference/upload-file`
- `PUT /api/catalog/mtg/set-reference/{set_id}`
- `DELETE /api/catalog/mtg/set-reference/{set_id}`

### Integrations

Base: `/api/integrations`

eBay (`/api/integrations/ebay`)

App management (all require a user session):

- `GET /api/integrations/ebay/auth/apps` — list all eBay apps linked to the current user; returns `app_name`, `app_code`, `environment`, `description`, `is_connected` (non-expired refresh token exists), `token_expires_at`, `other_user_count`
- `GET /api/integrations/ebay/auth/apps/{app_code}/rate-limits` — fetch live eBay Developer Analytics rate limits for an app via client credentials flow; returns per-resource `limit`, `remaining`, `reset`, `time_window_seconds`
- `POST /api/integrations/ebay/auth/admin/apps` — register eBay app (admin)
- `PATCH /api/integrations/ebay/auth/admin/apps/{app_code}/redirect-uri` — update stored redirect URI for a registered app (admin)

OAuth flow:

- `POST /api/integrations/ebay/auth/app/login` — start OAuth flow; returns authorization URL; requires user session
- `GET /api/integrations/ebay/auth/callback` — eBay OAuth callback; exchanges code for tokens, sets `ebay_access_{app_code}` httponly cookie; redirects to `{FRONTEND_BASE_URL}/ebay/connected?status=authorized&app_code={app_code}` on success or `?status=error&message=...` on failure
- `POST /api/integrations/ebay/auth/exange_token` — exchange stored refresh token for new access token, sets `ebay_access_{app_code}` cookie

eBay OAuth scope notes:
- Two levels of scope assignment: `scope_app` (scopes granted to the app by eBay) and `scopes_user` (per-user subset, enforced by DB trigger `trg_scopes_user_subset_check`). Both must be populated at registration time — `scopes_user` rows must be inserted after `scope_app` or the trigger blocks the insert.
- The `scope` query parameter in the authorization URL must use **raw URLs** (e.g. `https://api.ebay.com/oauth/api_scope/sell.inventory.readonly`). eBay rejects percent-encoded scope URL characters (`%3A`, `%2F`). Spaces between scopes must be encoded as `%20`.
- Refresh tokens are stored encrypted (`pgp_sym_encrypt`, AES-256) in `app_integration.ebay_refresh_tokens`, one row per `(user_id, app_id)`. Access tokens are never written to disk — cached in Redis (`REDIS_CACHE_URL`, db 1) with TTY = `expires_in - 60s`.
- eBay sandbox may truncate or drop the `state` parameter on callback. The fallback is `get_latest_pending_request()` from `log_oauth_request`.
- `GET /api/integrations/ebay/search/` — search listings (requires `app_code` and `q`)

Listing endpoints (all require a user session and an `app_code` query parameter):

- `POST /api/integrations/ebay/listing/` — create listing; requires `Idempotency-Key` header (400 if absent); uses Redis SETNX to short-circuit duplicate creates
- `GET /api/integrations/ebay/listing/active` — paginated active listings (`limit`, `offset`); returns `PaginatedResponse`
- `GET /api/integrations/ebay/listing/history` — paginated order fulfillment history (`limit`, `offset`); returns `PaginatedResponse`
- `PUT /api/integrations/ebay/listing/{item_id}` — update an existing listing; body `ItemID` must match the URL `item_id`
- `DELETE /api/integrations/ebay/listing/{item_id}` — end a listing; optional `ending_reason` query param (default `NotAvailable`)

Shopify (`/api/integrations/shopify`)

- `POST /api/integrations/shopify/data_loading/load_data`
- `POST /api/integrations/shopify/data_loading/stage_data`
- `POST /api/integrations/shopify/shop-meta/theme/`
- `POST /api/integrations/shopify/shop-meta/theme/collection`
- `POST /api/integrations/shopify/shop-meta/market/`
- `GET /api/integrations/shopify/shop-meta/market/`
- `GET /api/integrations/shopify/shop-meta/market/{market_id}`
- `POST /api/integrations/shopify/shop-meta/collection/`
- `POST /api/integrations/shopify/shop-meta/collection/bulk`

MTGStock (`/api/integrations/mtg_stock`)

- `POST /api/integrations/mtg_stock/stage`
- `POST /api/integrations/mtg_stock/load_ids`
- `GET /api/integrations/mtg_stock/load` — accepts either `print_ids[]=...` or `range_start` + `range_end`

### Ops / Integrity

Base: `/api/ops`

Integrity (`/api/ops/integrity`)

- `GET /api/ops/integrity/scryfall/run-diff?ingestion_run_id=<id>` — post-run diagnostic report for the most recent (or specified) Scryfall pipeline run; reads `ops.ingestion_runs`, `ops.ingestion_run_steps`, and `ops.ingestion_run_metrics`
- `GET /api/ops/integrity/scryfall/checks` — runs 24 orphan/loose-data checks across `card_catalog`, `ops`, and `pricing` schemas; returns `errors` and `warnings` lists
- `GET /api/ops/integrity/public-schema-leak` — confirms no app objects have leaked into the public schema (tables, views, sequences, functions, `search_path`); extension-owned objects excluded

All three endpoints are pure SELECTs (zero side effects) and always return HTTP 200; severity is conveyed in the payload's `errors` and `warnings` arrays.

## What to keep updated

- If you add/remove routers under `src/automana/api/routers/`, update the “Endpoints” section.
- If auth changes (JWT header vs cookie), update the “Authentication” section and examples.
- If you standardize error responses, update “Errors” with the canonical shape.

