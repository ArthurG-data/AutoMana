# Forgot Password / Password Reset — Design Spec

**Date:** 2026-05-21  
**Status:** Approved

---

## Overview

Wire the dormant "Forgot?" link on the login page into a full forgot-password → email → reset flow. Uses DB-backed one-time tokens, Resend for transactional email, and a new `/reset-password` frontend route.

---

## Architecture

Strict layered architecture is preserved throughout:  
`Router → ServiceManager → Service → Repository → DB`

---

## Backend

### Database — Migration 43

New table `password_reset_tokens`:

```sql
CREATE TABLE password_reset_tokens (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES users(unique_id) ON DELETE CASCADE,
    token_hash    TEXT NOT NULL UNIQUE,   -- SHA-256 of the raw token
    expires_at    TIMESTAMPTZ NOT NULL,
    used_at       TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ON password_reset_tokens (user_id);
CREATE INDEX ON password_reset_tokens (expires_at);
```

File: `src/automana/database/SQL/migrations/migration_43_password_reset_tokens.sql`

### Repository

New `PasswordResetRepository` at `src/automana/api/repositories/auth/password_reset_repository.py`:

- `create(user_id, token_hash, expires_at) → dict`
- `get_by_token_hash(token_hash) → dict | None`
- `mark_used(token_id) → None`
- `invalidate_for_user(user_id) → None` — deletes unused, unexpired tokens for a user before creating a new one

### Services

Two new functions registered with `ServiceRegistry`, in `src/automana/api/services/auth/password_reset_service.py`:

**`auth.password.request_reset`** — `db_repositories=['user', 'password_reset']`
1. Look up user by email via `UserRepository.get_by_email`. If not found, return silently (no error — prevents user enumeration).
2. Call `PasswordResetRepository.invalidate_for_user(user_id)` to clear any prior unused tokens.
3. Generate a 32-byte random token via `secrets.token_urlsafe(32)`.
4. Hash it with `hashlib.sha256(token.encode()).hexdigest()`.
5. Store the hash with `expires_at = now + 30 minutes`.
6. Call `EmailService.send_reset_email(to=user.email, token=raw_token)`.
7. Return `{"status": "ok"}`.

**`auth.password.reset_password`** — `db_repositories=['user', 'password_reset']`
1. Hash the incoming token with SHA-256.
2. Look up `PasswordResetRepository.get_by_token_hash(hash)`. If not found → raise `HTTPException(400, "Invalid or expired reset link")`.
3. Check `used_at IS NOT None` or `expires_at < now` → same 400 error.
4. Update `hashed_password` on the user via `UserRepository.update_password(user_id, new_hash)`.
5. Call `PasswordResetRepository.mark_used(token_id)`.
6. Invalidate all sessions for the user via `SessionRepository.invalidate_all_for_user(user_id)`.
7. Return `{"status": "ok"}`.

`UserRepository` needs a new method `update_password(user_id, hashed_password)`.  
`SessionRepository` needs a new method `invalidate_all_for_user(user_id)`.

### Endpoints

Added to the existing router at `src/automana/api/routers/users/auth.py`:

**`POST /api/users/auth/forgot-password`**
- Body: `{"email": "..."}`
- Always returns `200 {"message": "If that email exists, a reset link has been sent."}` — never reveals whether email exists.
- No authentication required.

**`POST /api/users/auth/reset-password`**
- Body: `{"token": "...", "new_password": "..."}`
- `new_password` minimum length 8 characters (Pydantic validation).
- Returns `200 {"message": "Password updated successfully."}` on success.
- Returns `400` for invalid/expired/already-used token.
- No authentication required.

### Pydantic Schemas

New file `src/automana/api/schemas/auth/password_reset.py`:
- `ForgotPasswordRequest(email: EmailStr)`
- `ResetPasswordRequest(token: str, new_password: str = Field(min_length=8))`

---

## Email Service

New file `src/automana/api/services/email/email_service.py`.

Uses the `resend` Python package. Sends a plain transactional email with inline HTML.

Reset link format: `{APP_BASE_URL}/reset-password?token={raw_token}`

**New settings** (in `core/settings.py`, all sourced from env vars):

| Setting | Default | Notes |
|---------|---------|-------|
| `RESEND_API_KEY` | `""` | Required in non-dev envs |
| `APP_BASE_URL` | `"http://localhost:5173"` | Used to build the reset link |
| `FROM_EMAIL` | `"noreply@automana.app"` | Resend verified sender |

**New env var entries** added to `config/env/.env.example`:
```
RESEND_API_KEY=
APP_BASE_URL=http://localhost:5173
FROM_EMAIL=noreply@automana.app
```

`resend` added to `requirements.txt`.

---

## Frontend

### Login Page — Third Mode

`src/frontend/src/routes/login.tsx`

- `Mode` type extended: `'login' | 'signup' | 'forgot'`
- The `<span className={styles.forgotLink}>Forgot?</span>` becomes a `<button>` that calls `switchMode('forgot')`
- In `'forgot'` mode, the right panel shows:
  - Title: "Reset password"
  - Subtitle: "Enter your email and we'll send you a reset link."
  - Single email field
  - "Send reset link →" submit button
  - Back-to-login link: "Remembered it? Log in"
- On success: the form area is replaced with a static confirmation:  
  "Check your inbox — a reset link is on its way."
- The left panel headline/copy updates to match the active mode (same pattern as login vs signup)
- Error handling: any non-2xx → "Something went wrong. Please try again."

### New Route — `/reset-password`

New file `src/frontend/src/routes/reset-password.tsx`  
Registered in the router the same way `/login` is.

Behavior:
1. On mount, read `?token=` from the URL search params.
2. If token is absent: show error state "Invalid or missing reset link." with a link back to `/login`.
3. Otherwise show:
   - "New password" input (type=password, min 8 chars)
   - "Confirm password" input
   - Client-side validation: passwords must match before submit
   - "Set new password →" button
4. On success: show "Password updated — redirecting to login..." then `navigate({ to: '/login' })` after 2 seconds.
5. On 400 from API: "This link has expired or has already been used." + link to `/login` to request a new one.
6. Left panel: same two-panel layout as the login page — reuse the card-art stack and logo mark.

### API Functions

Added to `src/frontend/src/features/auth/api.ts`:

```typescript
postForgotPassword(email: string): Promise<void>
// POST /api/users/auth/forgot-password

postResetPassword(token: string, newPassword: string): Promise<void>
// POST /api/users/auth/reset-password
```

---

## Security Properties

- **No user enumeration**: `forgot-password` always returns 200 regardless of whether the email exists.
- **One-time use**: tokens are marked `used_at` immediately on consumption; re-use returns 400.
- **Short expiry**: 30-minute window.
- **Plaintext never stored**: only the SHA-256 hash is written to the DB.
- **Prior tokens invalidated**: requesting a new reset link invalidates any outstanding unused token for that user.
- **Sessions invalidated on reset**: all active sessions are cleared when the password is changed.
- **Constant-time comparison**: using hash lookup (not string comparison) avoids timing attacks.

---

## Files Created / Modified

| Path | Action |
|------|--------|
| `src/automana/database/SQL/migrations/migration_43_password_reset_tokens.sql` | Create |
| `src/automana/api/repositories/auth/password_reset_repository.py` | Create |
| `src/automana/api/repositories/auth/session_repository.py` | Modify — add `invalidate_all_for_user` |
| `src/automana/api/repositories/user_management/user_repository.py` | Modify — add `update_password` |
| `src/automana/api/schemas/auth/password_reset.py` | Create |
| `src/automana/api/services/auth/password_reset_service.py` | Create |
| `src/automana/api/services/email/email_service.py` | Create |
| `src/automana/api/services/email/__init__.py` | Create |
| `src/automana/api/routers/users/auth.py` | Modify — add 2 endpoints |
| `src/automana/core/service_registry.py` | Modify — register `password_reset` repository |
| `src/automana/core/settings.py` | Modify — add 3 settings |
| `config/env/.env.example` | Modify — add 3 env vars |
| `requirements.txt` | Modify — add `resend` |
| `src/frontend/src/features/auth/api.ts` | Modify — add 2 functions |
| `src/frontend/src/routes/login.tsx` | Modify — add `'forgot'` mode |
| `src/frontend/src/routes/reset-password.tsx` | Create |
