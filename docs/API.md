
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
	- Returns a JSON token payload and sets cookies (including `session_id`).

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

Many endpoints return a standard shape defined in `backend/request_handling/StandardisedQueryResponse.py`.

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

- `POST /api/users/auth/token` — login, sets `session_id`
- `POST /api/users/auth/token/refresh` — refresh access token
- `POST /api/users/auth/logout` — logout (clears cookie)

Sessions (`/api/users/session`)

- `GET /api/users/session/{session_id}` — get one session
- `GET /api/users/session/` — search sessions (paginated)
- `DELETE /api/users/session/{session_id}/desactivate` — deactivate a session

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

- `GET /api/catalog/mtg/card-reference/{card_id}` — get card by id
- `GET /api/catalog/mtg/card-reference/` — search cards (paginated)
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

- `POST /api/integrations/ebay/auth/admin/apps` — register eBay app (admin)
- `POST /api/integrations/ebay/auth/app/login` — start OAuth flow (requires user session)
- `GET /api/integrations/ebay/auth/callback` — OAuth callback
- `POST /api/integrations/ebay/auth/exange_token` — exchange refresh token, sets `ebay_access_{app_code}` cookie
- `GET /api/integrations/ebay/search/` — search listings (requires `app_code` and `q`)
- `POST /api/integrations/ebay/listing/` — create listing (requires user session)
- `GET /api/integrations/ebay/listing/active` — active listings (requires user session)
- `GET /api/integrations/ebay/listing/history` — listing history (requires user session)
- `PUT /api/integrations/ebay/listing/{item_id}` — update listing (requires user session)

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

### Logs

Base: `/api/logs`

- `GET /api/logs/` — fetch logs with optional filters (`start_date`, `end_date`, `level`, `task_name`, `service_type`, `user`, `status`, `search`, `limit`, `offset`)

## What to keep updated

- If you add/remove routers under `backend/api/*`, update the “Endpoints” section.
- If auth changes (JWT header vs cookie), update the “Authentication” section and examples.
- If you standardize error responses, update “Errors” with the canonical shape.

