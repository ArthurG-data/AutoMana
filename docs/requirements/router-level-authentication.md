# Requirements: Router-Level Authentication

## Summary
Replace per-endpoint auth dependency injection with router-level dependency application. A single `get_current_active_user` dependency handles both cookie-based (browser) and Bearer token (CLI) authentication. Protected routers declare the dependency once; endpoints that need the user object still receive it via the existing `CurrentUserDep` pattern. Public routes (health check, card search) are explicitly excluded.

## Goals
- Eliminate redundant dependency declarations on every endpoint
- Support browser clients (httpOnly session cookie) and CLI clients (Bearer token) through one dependency
- Redirect browsers to `/login` on auth failure; return 401 JSON to programmatic callers
- Keep the `CurrentUserDep = Annotated[UserInDB, Depends(...)]` injection pattern for endpoints that need the user object

## Actors
- **Browser client**: sends session cookie set at login; expects redirect to `/login` on auth failure
- **CLI / programmatic client**: sends `Authorization: Bearer <access_token>`; expects 401 JSON on auth failure
- **Public client**: no credentials required for health check and public card search endpoints

## Happy Path
1. Client sends a request to a protected router
2. The router-level dependency `get_current_active_user` runs automatically
3. Dependency checks for a `session_id` cookie first
   - If present: validates session via `auth.session.get_user_from_session` service, returns `UserInDB`
4. If no cookie: checks `Authorization: Bearer <token>` header
   - If present: decodes and validates the JWT, looks up the user, returns `UserInDB`
5. Endpoint handler executes; if it declared `CurrentUserDep`, receives the resolved `UserInDB`

## Edge Cases & Error Handling
- **No cookie and no Bearer header**: check `Accept` header
  - Contains `text/html` → HTTP 302 redirect to `/login`
  - Otherwise → HTTP 401 JSON `{"detail": "Not authenticated"}`
- **Cookie present but session expired or not found**: same `Accept`-based split (redirect vs 401)
- **Bearer token present but invalid/expired**: 401 JSON regardless of `Accept` (CLI callers always get JSON)
- **Cookie present and Bearer present**: cookie takes priority; Bearer is ignored
- **Public routes** (health check, public card search): no dependency applied; always accessible without credentials

## Out of Scope
- Frontend login page implementation (redirect target `/login` is a placeholder)
- Role-based authorisation beyond "authenticated vs not"
- Token refresh flow
- Mixing cookie and Bearer on the same request

## Data
- No new data created or stored
- `UserInDB` resolved from existing session/user repositories via `ServiceManager`
- Session cookie name: `session_id`
- Bearer token: existing JWT signed with `settings.jwt_secret_key` / `settings.jwt_algorithm`

## Integrations
- `auth.session.get_user_from_session` service (session → user lookup)
- `check_token_validity` helper in `auth_service.py` (Bearer JWT decode)
- FastAPI router `dependencies=[...]` parameter for router-level injection

## Constraints
- Must use FastAPI's `dependencies=[Depends(...)]` on the `APIRouter` constructor — not per-endpoint
- Endpoints that need the user object continue to declare `CurrentUserDep` as a parameter; FastAPI deduplicates the dependency call automatically
- `/login` redirect URL is a placeholder; must be easy to update via a single config value
- `Accept: text/html` is the signal for browser vs CLI — no custom headers required

## Success Criteria
- No protected endpoint declares `CurrentUserDep` or any auth dependency in its own signature unless it needs the user object
- A request with a valid session cookie to any protected route succeeds
- A request with a valid Bearer token to any protected route succeeds
- A browser request (Accept: text/html) with no credentials is redirected to `/login`
- A CLI request (Accept: application/json) with no credentials receives HTTP 401 JSON
- Health check and public card search remain accessible without credentials
- All existing auth unit tests pass
