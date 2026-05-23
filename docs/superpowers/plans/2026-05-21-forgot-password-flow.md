# Forgot Password / Password Reset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the dormant "Forgot?" link on the login page into a complete forgot-password → Resend email → reset-password flow, using DB-backed one-time tokens.

**Architecture:** DB-backed tokens in `user_management.password_reset_tokens` (SHA-256 hash stored, plaintext never persisted). Two new API endpoints (`/api/users/auth/forgot-password`, `/api/users/auth/reset-password`) wired through the standard Router → ServiceManager → Service → Repository chain. Frontend adds a third "forgot" mode to the login page and a new `/reset-password` route.

**Tech Stack:** Python/FastAPI, asyncpg, `resend` (Python SDK), bcrypt, TanStack Router (file-based, auto-generates `routeTree.gen.ts`), Vitest + React Testing Library.

---

## File Map

| File | Action |
|------|--------|
| `src/automana/database/SQL/schemas/03_users.sql` | Modify — add `password_reset_tokens` table |
| `src/automana/database/SQL/migrations/migration_43_password_reset_tokens.sql` | Create — for existing dev/prod DBs |
| `src/automana/api/repositories/auth/password_reset_repository.py` | Create |
| `src/automana/api/repositories/auth/session_repository.py` | Modify — add `invalidate_all_for_user` |
| `src/automana/api/repositories/user_management/user_repository.py` | Modify — add `update_password` |
| `src/automana/core/service_registry.py` | Modify — register `password_reset` repo |
| `src/automana/core/settings.py` | Modify — add 3 new settings |
| `config/env/.env.example` | Modify — add 3 env vars |
| `pyproject.toml` | Modify — add `resend` dependency |
| `src/automana/api/services/email/__init__.py` | Create (empty) |
| `src/automana/api/services/email/email_service.py` | Create |
| `src/automana/api/schemas/auth/password_reset.py` | Create |
| `src/automana/api/services/auth/password_reset_service.py` | Create |
| `src/automana/api/routers/users/auth.py` | Modify — add 2 endpoints |
| `tests/unit/api/services/auth/test_password_reset_service.py` | Create |
| `tests/integration/api/test_password_reset.py` | Create |
| `src/frontend/src/features/auth/api.ts` | Modify — add 2 functions |
| `src/frontend/src/routes/login.tsx` | Modify — add `'forgot'` mode |
| `src/frontend/src/routes/reset-password.tsx` | Create |
| `src/frontend/src/routes/__root.tsx` | Modify — add `/reset-password` to PUBLIC_PATHS |

---

## Task 1: Database — schema + migration

**Files:**
- Modify: `src/automana/database/SQL/schemas/03_users.sql`
- Create: `src/automana/database/SQL/migrations/migration_43_password_reset_tokens.sql`

- [ ] **Step 1: Add table to `03_users.sql` (before the final `COMMIT;`)**

  Open `src/automana/database/SQL/schemas/03_users.sql`. Find the line `COMMIT;` at the very end (after all the triggers). Insert the following block immediately before it:

  ```sql
  CREATE TABLE IF NOT EXISTS user_management.password_reset_tokens (
      id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
      user_id       UUID NOT NULL REFERENCES user_management.users(unique_id) ON DELETE CASCADE,
      token_hash    TEXT NOT NULL UNIQUE,
      expires_at    TIMESTAMPTZ NOT NULL,
      used_at       TIMESTAMPTZ,
      created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
  );
  CREATE INDEX IF NOT EXISTS idx_prt_user_id ON user_management.password_reset_tokens (user_id);
  CREATE INDEX IF NOT EXISTS idx_prt_expires_at ON user_management.password_reset_tokens (expires_at);
  ```

- [ ] **Step 2: Create migration file for existing dev/prod DBs**

  Create `src/automana/database/SQL/migrations/migration_43_password_reset_tokens.sql`:

  ```sql
  -- migration_43: add password_reset_tokens table for forgot-password flow
  CREATE TABLE IF NOT EXISTS user_management.password_reset_tokens (
      id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
      user_id       UUID NOT NULL REFERENCES user_management.users(unique_id) ON DELETE CASCADE,
      token_hash    TEXT NOT NULL UNIQUE,
      expires_at    TIMESTAMPTZ NOT NULL,
      used_at       TIMESTAMPTZ,
      created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
  );
  CREATE INDEX IF NOT EXISTS idx_prt_user_id ON user_management.password_reset_tokens (user_id);
  CREATE INDEX IF NOT EXISTS idx_prt_expires_at ON user_management.password_reset_tokens (expires_at);
  ```

- [ ] **Step 3: Apply migration to dev DB**

  ```bash
  docker exec -i automana-postgres-dev psql -U automana_admin automana < src/automana/database/SQL/migrations/migration_43_password_reset_tokens.sql
  ```

  Expected: `CREATE TABLE`, `CREATE INDEX`, `CREATE INDEX` (no errors).

- [ ] **Step 4: Commit**

  ```bash
  git add src/automana/database/SQL/schemas/03_users.sql \
          src/automana/database/SQL/migrations/migration_43_password_reset_tokens.sql
  git commit -m "feat(db): add password_reset_tokens table (migration_43)"
  ```

---

## Task 2: Repository layer

**Files:**
- Create: `src/automana/api/repositories/auth/password_reset_repository.py`
- Modify: `src/automana/api/repositories/auth/session_repository.py`
- Modify: `src/automana/api/repositories/user_management/user_repository.py`

- [ ] **Step 1: Create `PasswordResetRepository`**

  Create `src/automana/api/repositories/auth/password_reset_repository.py`:

  ```python
  from uuid import UUID
  from datetime import datetime
  from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository


  class PasswordResetRepository(AbstractRepository):
      def __init__(self, connection, executor=None):
          super().__init__(connection, executor)

      @property
      def name(self) -> str:
          return "PasswordResetRepository"

      async def create(self, user_id: UUID, token_hash: str, expires_at: datetime) -> dict:
          query = """
          INSERT INTO user_management.password_reset_tokens (user_id, token_hash, expires_at)
          VALUES ($1, $2, $3)
          RETURNING *;
          """
          result = await self.execute_query(query, (user_id, token_hash, expires_at))
          return result[0] if result else None

      async def get_by_token_hash(self, token_hash: str) -> dict | None:
          query = """
          SELECT * FROM user_management.password_reset_tokens
          WHERE token_hash = $1;
          """
          result = await self.execute_query(query, (token_hash,))
          return result[0] if result else None

      async def mark_used(self, token_id: UUID) -> None:
          query = """
          UPDATE user_management.password_reset_tokens
          SET used_at = NOW()
          WHERE id = $1;
          """
          await self.execute_command(query, (token_id,))

      async def invalidate_for_user(self, user_id: UUID) -> None:
          query = """
          DELETE FROM user_management.password_reset_tokens
          WHERE user_id = $1 AND used_at IS NULL AND expires_at > NOW();
          """
          await self.execute_command(query, (user_id,))

      async def list(self):
          raise NotImplementedError
  ```

- [ ] **Step 2: Add `invalidate_all_for_user` to `SessionRepository`**

  Open `src/automana/api/repositories/auth/session_repository.py`. Add this method at the end, before the closing of the class:

  ```python
      async def invalidate_all_for_user(self, user_id: UUID) -> None:
          sessions = await self.get_by_user_id(user_id)
          for session in sessions:
              await self.invalidate_session(session["session_id"], "password-reset")
  ```

- [ ] **Step 3: Add `update_password` to `UserRepository`**

  Open `src/automana/api/repositories/user_management/user_repository.py`. Add this method after the existing `update` method:

  ```python
      async def update_password(self, user_id: UUID, hashed_password: str) -> None:
          query = """
          UPDATE users SET hashed_password = $1, updated_at = NOW()
          WHERE unique_id = $2;
          """
          await self.execute_command(query, (hashed_password, user_id))
  ```

- [ ] **Step 4: Register `PasswordResetRepository` in service registry**

  Open `src/automana/core/service_registry.py`. Find the `#Auth repositories` block (around line 157). Add the new registration after the existing `"session"` registration:

  ```python
  ServiceRegistry.register_db_repository(
      "password_reset",
      "automana.api.repositories.auth.password_reset_repository",
      "PasswordResetRepository",
  )
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add src/automana/api/repositories/auth/password_reset_repository.py \
          src/automana/api/repositories/auth/session_repository.py \
          src/automana/api/repositories/user_management/user_repository.py \
          src/automana/core/service_registry.py
  git commit -m "feat(auth): add PasswordResetRepository and update Session/UserRepository"
  ```

---

## Task 3: Settings + Resend dependency + Email service

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/automana/core/settings.py`
- Modify: `config/env/.env.example`
- Create: `src/automana/api/services/email/__init__.py`
- Create: `src/automana/api/services/email/email_service.py`

- [ ] **Step 1: Add `resend` to `pyproject.toml`**

  Open `pyproject.toml`. Find the `dependencies = [` block. Add `"resend>=2.0.0"` to the list (keep alphabetical or append before the closing `]`):

  ```toml
  "resend>=2.0.0",
  ```

- [ ] **Step 2: Install the new dependency**

  ```bash
  pip install -e .
  python -c "import resend; print(resend.__version__)"
  ```

  Expected: a version string printed (e.g., `2.x.x`).

- [ ] **Step 3: Add settings to `src/automana/core/settings.py`**

  Open `src/automana/core/settings.py`. Find the `# eBay` settings block (around the `ebay_app_id` line). Add the following block immediately before it:

  ```python
      # Email / password reset
      resend_api_key: str = Field(default="")
      app_base_url: str = Field(default="http://localhost:5173")
      from_email: str = Field(default="noreply@automana.app")
  ```

- [ ] **Step 4: Add env vars to `.env.example`**

  Open `config/env/.env.example`. Append:

  ```
  # Email (Resend) — used for password reset emails
  RESEND_API_KEY=
  APP_BASE_URL=http://localhost:5173
  FROM_EMAIL=noreply@automana.app
  ```

- [ ] **Step 5: Create email service**

  Create `src/automana/api/services/email/__init__.py` (empty file).

  Create `src/automana/api/services/email/email_service.py`:

  ```python
  import logging
  import resend
  from automana.core.config.settings import get_settings

  logger = logging.getLogger(__name__)


  class EmailService:
      @staticmethod
      def send_reset_email(to: str, token: str) -> None:
          settings = get_settings()
          resend.api_key = settings.resend_api_key
          reset_url = f"{settings.app_base_url}/reset-password?token={token}"
          resend.Emails.send({
              "from": settings.from_email,
              "to": [to],
              "subject": "Reset your AutoMana password",
              "html": (
                  f"<p>You requested a password reset for your AutoMana account.</p>"
                  f'<p><a href="{reset_url}">Click here to reset your password</a></p>'
                  f"<p>This link expires in 30 minutes.</p>"
                  f"<p>If you didn't request this, you can safely ignore this email.</p>"
              ),
          })
          logger.info("password_reset_email_sent", extra={"to": to})
  ```

- [ ] **Step 6: Commit**

  ```bash
  git add pyproject.toml \
          src/automana/core/settings.py \
          config/env/.env.example \
          src/automana/api/services/email/__init__.py \
          src/automana/api/services/email/email_service.py
  git commit -m "feat(email): add Resend email service and password-reset settings"
  ```

---

## Task 4: Password reset service

**Files:**
- Create: `src/automana/api/services/auth/password_reset_service.py`
- Create: `tests/unit/api/services/auth/test_password_reset_service.py`

- [ ] **Step 1: Write failing unit tests**

  Create `tests/unit/api/services/auth/test_password_reset_service.py`:

  ```python
  import hashlib
  import pytest
  from datetime import datetime, timezone, timedelta
  from unittest.mock import AsyncMock, MagicMock, patch
  from uuid import uuid4

  pytestmark = [pytest.mark.unit, pytest.mark.service]


  def _make_user(email="user@example.com"):
      return {
          "unique_id": uuid4(),
          "email": email,
          "username": "testuser",
          "disabled": False,
      }


  def _make_token_row(user_id, raw_token, minutes_until_expiry=30):
      token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
      return {
          "id": uuid4(),
          "user_id": user_id,
          "token_hash": token_hash,
          "expires_at": datetime.now(timezone.utc) + timedelta(minutes=minutes_until_expiry),
          "used_at": None,
      }


  class TestRequestReset:
      async def test_unknown_email_returns_ok_silently(self):
          """No error raised when email not found (prevents user enumeration)."""
          from automana.api.services.auth.password_reset_service import request_reset

          user_repo = AsyncMock()
          user_repo.get_by_email.return_value = None
          reset_repo = AsyncMock()

          result = await request_reset(
              user_repository=user_repo,
              password_reset_repository=reset_repo,
              email="nobody@example.com",
          )

          assert result == {"status": "ok"}
          reset_repo.invalidate_for_user.assert_not_called()
          reset_repo.create.assert_not_called()

      async def test_known_email_creates_token_and_sends_email(self):
          """Creates a token and calls EmailService when email exists."""
          from automana.api.services.auth.password_reset_service import request_reset

          user = _make_user()
          user_repo = AsyncMock()
          user_repo.get_by_email.return_value = user
          reset_repo = AsyncMock()
          reset_repo.create.return_value = {"id": uuid4()}

          with patch(
              "automana.api.services.auth.password_reset_service.EmailService.send_reset_email"
          ) as mock_send:
              result = await request_reset(
                  user_repository=user_repo,
                  password_reset_repository=reset_repo,
                  email=user["email"],
              )

          assert result == {"status": "ok"}
          reset_repo.invalidate_for_user.assert_called_once_with(user["unique_id"])
          reset_repo.create.assert_called_once()
          mock_send.assert_called_once()
          call_kwargs = mock_send.call_args.kwargs
          assert call_kwargs["to"] == user["email"]
          assert len(call_kwargs["token"]) > 0


  class TestResetPassword:
      async def test_invalid_token_raises_400(self):
          """Returns 400 when token hash not found in DB."""
          from fastapi import HTTPException
          from automana.api.services.auth.password_reset_service import reset_password

          user_repo = AsyncMock()
          reset_repo = AsyncMock()
          reset_repo.get_by_token_hash.return_value = None
          session_repo = AsyncMock()

          with pytest.raises(HTTPException) as exc:
              await reset_password(
                  user_repository=user_repo,
                  password_reset_repository=reset_repo,
                  session_repository=session_repo,
                  token="badtoken",
                  new_password="NewPass123!",
              )

          assert exc.value.status_code == 400

      async def test_expired_token_raises_400(self):
          """Returns 400 when token is past its expiry."""
          from fastapi import HTTPException
          from automana.api.services.auth.password_reset_service import reset_password

          user_id = uuid4()
          expired_row = {
              "id": uuid4(),
              "user_id": user_id,
              "token_hash": "any",
              "expires_at": datetime.now(timezone.utc) - timedelta(minutes=1),
              "used_at": None,
          }
          user_repo = AsyncMock()
          reset_repo = AsyncMock()
          reset_repo.get_by_token_hash.return_value = expired_row
          session_repo = AsyncMock()

          with pytest.raises(HTTPException) as exc:
              await reset_password(
                  user_repository=user_repo,
                  password_reset_repository=reset_repo,
                  session_repository=session_repo,
                  token="expiredtoken",
                  new_password="NewPass123!",
              )

          assert exc.value.status_code == 400

      async def test_already_used_token_raises_400(self):
          """Returns 400 when token was already consumed."""
          from fastapi import HTTPException
          from automana.api.services.auth.password_reset_service import reset_password

          user_id = uuid4()
          used_row = {
              "id": uuid4(),
              "user_id": user_id,
              "token_hash": "any",
              "expires_at": datetime.now(timezone.utc) + timedelta(minutes=15),
              "used_at": datetime.now(timezone.utc) - timedelta(minutes=5),
          }
          user_repo = AsyncMock()
          reset_repo = AsyncMock()
          reset_repo.get_by_token_hash.return_value = used_row
          session_repo = AsyncMock()

          with pytest.raises(HTTPException) as exc:
              await reset_password(
                  user_repository=user_repo,
                  password_reset_repository=reset_repo,
                  session_repository=session_repo,
                  token="usedtoken",
                  new_password="NewPass123!",
              )

          assert exc.value.status_code == 400

      async def test_valid_token_updates_password_and_invalidates_sessions(self):
          """Valid token → password updated, token marked used, sessions cleared."""
          from automana.api.services.auth.password_reset_service import reset_password

          user_id = uuid4()
          raw_token = "validtoken"
          token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
          token_row = {
              "id": uuid4(),
              "user_id": user_id,
              "token_hash": token_hash,
              "expires_at": datetime.now(timezone.utc) + timedelta(minutes=25),
              "used_at": None,
          }
          user_repo = AsyncMock()
          reset_repo = AsyncMock()
          reset_repo.get_by_token_hash.return_value = token_row
          session_repo = AsyncMock()

          result = await reset_password(
              user_repository=user_repo,
              password_reset_repository=reset_repo,
              session_repository=session_repo,
              token=raw_token,
              new_password="NewPass123!",
          )

          assert result == {"status": "ok"}
          user_repo.update_password.assert_called_once()
          update_call = user_repo.update_password.call_args
          assert update_call.kwargs["user_id"] == user_id
          # Stored password must be a bcrypt hash, not plaintext
          assert update_call.kwargs["hashed_password"] != "NewPass123!"
          assert update_call.kwargs["hashed_password"].startswith("$2b$")
          reset_repo.mark_used.assert_called_once_with(token_row["id"])
          session_repo.invalidate_all_for_user.assert_called_once_with(user_id)
  ```

- [ ] **Step 2: Run tests to confirm they fail**

  ```bash
  pytest tests/unit/api/services/auth/test_password_reset_service.py -v
  ```

  Expected: `ModuleNotFoundError` or `ImportError` (module doesn't exist yet).

- [ ] **Step 3: Implement the service**

  Create `src/automana/api/services/auth/password_reset_service.py`:

  ```python
  import hashlib
  import logging
  import secrets
  from datetime import datetime, timezone, timedelta

  from fastapi import HTTPException

  from automana.api.repositories.auth.password_reset_repository import PasswordResetRepository
  from automana.api.repositories.auth.session_repository import SessionRepository
  from automana.api.repositories.user_management.user_repository import UserRepository
  from automana.api.services.auth.auth import get_hash_password
  from automana.api.services.email.email_service import EmailService
  from automana.core.service_registry import ServiceRegistry

  logger = logging.getLogger(__name__)

  _INVALID_MSG = "Invalid or expired reset link"


  @ServiceRegistry.register(
      "auth.password.request_reset",
      db_repositories=["user", "password_reset"],
  )
  async def request_reset(
      user_repository: UserRepository,
      password_reset_repository: PasswordResetRepository,
      email: str,
  ) -> dict:
      user = await user_repository.get_by_email(email)
      if not user:
          logger.info("password_reset_unknown_email", extra={"email": email})
          return {"status": "ok"}

      await password_reset_repository.invalidate_for_user(user["unique_id"])

      raw_token = secrets.token_urlsafe(32)
      token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
      expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
      await password_reset_repository.create(
          user_id=user["unique_id"],
          token_hash=token_hash,
          expires_at=expires_at,
      )

      EmailService.send_reset_email(to=user["email"], token=raw_token)
      logger.info("password_reset_requested", extra={"user_id": str(user["unique_id"])})
      return {"status": "ok"}


  @ServiceRegistry.register(
      "auth.password.reset_password",
      db_repositories=["user", "password_reset", "session"],
  )
  async def reset_password(
      user_repository: UserRepository,
      password_reset_repository: PasswordResetRepository,
      session_repository: SessionRepository,
      token: str,
      new_password: str,
  ) -> dict:
      token_hash = hashlib.sha256(token.encode()).hexdigest()
      row = await password_reset_repository.get_by_token_hash(token_hash)

      if not row:
          raise HTTPException(status_code=400, detail=_INVALID_MSG)
      if row["used_at"] is not None:
          raise HTTPException(status_code=400, detail=_INVALID_MSG)
      if row["expires_at"] < datetime.now(timezone.utc):
          raise HTTPException(status_code=400, detail=_INVALID_MSG)

      hashed = get_hash_password(new_password)
      await user_repository.update_password(user_id=row["user_id"], hashed_password=hashed)
      await password_reset_repository.mark_used(row["id"])
      await session_repository.invalidate_all_for_user(row["user_id"])

      logger.info("password_reset_complete", extra={"user_id": str(row["user_id"])})
      return {"status": "ok"}
  ```

- [ ] **Step 4: Run tests — expect pass**

  ```bash
  pytest tests/unit/api/services/auth/test_password_reset_service.py -v
  ```

  Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add src/automana/api/services/auth/password_reset_service.py \
          tests/unit/api/services/auth/test_password_reset_service.py
  git commit -m "feat(auth): implement password reset service with unit tests"
  ```

---

## Task 5: Pydantic schemas + Router endpoints

**Files:**
- Create: `src/automana/api/schemas/auth/password_reset.py`
- Modify: `src/automana/api/routers/users/auth.py`

- [ ] **Step 1: Create Pydantic schemas**

  Create `src/automana/api/schemas/auth/password_reset.py`:

  ```python
  from pydantic import BaseModel, EmailStr, Field


  class ForgotPasswordRequest(BaseModel):
      email: EmailStr


  class ResetPasswordRequest(BaseModel):
      token: str
      new_password: str = Field(min_length=8)
  ```

- [ ] **Step 2: Add endpoints to the router**

  Open `src/automana/api/routers/users/auth.py`. Add the following imports at the top (after the existing imports):

  ```python
  from automana.api.schemas.auth.password_reset import ForgotPasswordRequest, ResetPasswordRequest
  ```

  Then append two new endpoints at the bottom of the file:

  ```python
  @authentification_router.post(
      '/forgot-password',
      summary="Request a password reset link",
      description=(
          "Accepts an email address and sends a reset link if the email is registered. "
          "Always returns 200 to prevent user enumeration."
      ),
      status_code=200,
      operation_id="auth_forgot_password",
      responses={**_AUTH_ERRORS},
  )
  async def forgot_password(
      body: ForgotPasswordRequest,
      service_manager: ServiceManagerDep,
  ):
      await service_manager.execute_service(
          "auth.password.request_reset",
          email=body.email,
      )
      return {"message": "If that email exists, a reset link has been sent."}


  @authentification_router.post(
      '/reset-password',
      summary="Reset password using a token from the reset email",
      description=(
          "Validates the one-time reset token, updates the user's password, "
          "and invalidates all active sessions. Returns 400 if the token is "
          "invalid, expired, or already used."
      ),
      status_code=200,
      operation_id="auth_reset_password",
      responses={
          400: {"description": "Invalid, expired, or already-used reset token"},
          **_AUTH_ERRORS,
      },
  )
  async def reset_password_endpoint(
      body: ResetPasswordRequest,
      service_manager: ServiceManagerDep,
  ):
      await service_manager.execute_service(
          "auth.password.reset_password",
          token=body.token,
          new_password=body.new_password,
      )
      return {"message": "Password updated successfully."}
  ```

- [ ] **Step 3: Verify the app starts cleanly**

  ```bash
  python -c "from automana.api.main import app; print('OK')"
  ```

  Expected: `OK` (no import errors).

- [ ] **Step 4: Commit**

  ```bash
  git add src/automana/api/schemas/auth/password_reset.py \
          src/automana/api/routers/users/auth.py
  git commit -m "feat(auth): add forgot-password and reset-password endpoints"
  ```

---

## Task 6: Integration test — full reset flow

**Files:**
- Create: `tests/integration/api/test_password_reset.py`

- [ ] **Step 1: Write the integration test**

  Create `tests/integration/api/test_password_reset.py`:

  ```python
  """
  Integration tests for the forgot-password / reset-password flow.
  Covers: request reset, consume token, login with new password, reject old password, reject reuse.
  """
  from unittest.mock import patch

  import pytest

  pytestmark = [pytest.mark.integration, pytest.mark.api]


  async def test_forgot_password_unknown_email_returns_200(client):
      """Always 200 — no enumeration leak."""
      response = await client.post(
          "/api/users/auth/forgot-password",
          json={"email": "nobody@doesnotexist.example"},
      )
      assert response.status_code == 200
      assert "reset link" in response.json()["message"]


  async def test_full_reset_flow(client, created_user, test_user_data):
      """Request reset → use token → login with new password → old password rejected."""
      captured = {}

      with patch(
          "automana.api.services.auth.password_reset_service.EmailService.send_reset_email"
      ) as mock_send:
          mock_send.side_effect = lambda to, token: captured.update({"token": token})
          response = await client.post(
              "/api/users/auth/forgot-password",
              json={"email": test_user_data["email"]},
          )

      assert response.status_code == 200
      assert "token" in captured, "EmailService.send_reset_email was not called"

      raw_token = captured["token"]
      new_password = "NewPassword456!"

      # Reset the password
      reset_response = await client.post(
          "/api/users/auth/reset-password",
          json={"token": raw_token, "new_password": new_password},
      )
      assert reset_response.status_code == 200

      # New password works
      login_response = await client.post(
          "/api/users/auth/token",
          content=f"username={test_user_data['email']}&password={new_password}",
          headers={"Content-Type": "application/x-www-form-urlencoded"},
      )
      assert login_response.status_code == 200

      # Old password rejected
      old_login = await client.post(
          "/api/users/auth/token",
          content=f"username={test_user_data['email']}&password={test_user_data['password']}",
          headers={"Content-Type": "application/x-www-form-urlencoded"},
      )
      assert old_login.status_code == 401


  async def test_reset_token_is_single_use(client, created_user, test_user_data):
      """Using the same token twice returns 400 on the second attempt."""
      captured = {}

      with patch(
          "automana.api.services.auth.password_reset_service.EmailService.send_reset_email"
      ) as mock_send:
          mock_send.side_effect = lambda to, token: captured.update({"token": token})
          await client.post(
              "/api/users/auth/forgot-password",
              json={"email": test_user_data["email"]},
          )

      raw_token = captured["token"]

      first = await client.post(
          "/api/users/auth/reset-password",
          json={"token": raw_token, "new_password": "FirstNewPass1!"},
      )
      assert first.status_code == 200

      second = await client.post(
          "/api/users/auth/reset-password",
          json={"token": raw_token, "new_password": "SecondNewPass1!"},
      )
      assert second.status_code == 400


  async def test_reset_with_bogus_token_returns_400(client):
      """Completely invalid token returns 400."""
      response = await client.post(
          "/api/users/auth/reset-password",
          json={"token": "not-a-real-token", "new_password": "SomePass123!"},
      )
      assert response.status_code == 400


  async def test_reset_password_too_short_returns_422(client):
      """Password shorter than 8 chars fails Pydantic validation."""
      response = await client.post(
          "/api/users/auth/reset-password",
          json={"token": "anytoken", "new_password": "short"},
      )
      assert response.status_code == 422
  ```

- [ ] **Step 2: Run integration tests**

  ```bash
  pytest tests/integration/api/test_password_reset.py -v
  ```

  Expected: all 5 tests PASS. (Requires Docker containers running — the session-scoped fixtures spin them up automatically.)

- [ ] **Step 3: Commit**

  ```bash
  git add tests/integration/api/test_password_reset.py
  git commit -m "test(auth): integration tests for forgot-password / reset-password flow"
  ```

---

## Task 7: Frontend — API functions

**Files:**
- Modify: `src/frontend/src/features/auth/api.ts`

- [ ] **Step 1: Add the two API functions**

  Open `src/frontend/src/features/auth/api.ts`. Append at the end of the file:

  ```typescript
  /**
   * POST /api/users/auth/forgot-password
   * Always resolves (server returns 200 regardless of whether email exists).
   */
  export async function postForgotPassword(email: string): Promise<void> {
    const res = await fetch('/api/users/auth/forgot-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    })
    if (!res.ok) {
      const detail = await res.json().catch(() => ({})) as { detail?: string }
      throw Object.assign(new Error(detail.detail ?? 'Request failed'), { status: res.status })
    }
  }

  /**
   * POST /api/users/auth/reset-password
   * token: raw token from the reset link query param
   * newPassword: the user's chosen new password (min 8 chars)
   */
  export async function postResetPassword(token: string, newPassword: string): Promise<void> {
    const res = await fetch('/api/users/auth/reset-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, new_password: newPassword }),
    })
    if (!res.ok) {
      const detail = await res.json().catch(() => ({})) as { detail?: string }
      throw Object.assign(new Error(detail.detail ?? 'Reset failed'), { status: res.status })
    }
  }
  ```

- [ ] **Step 2: Verify TypeScript compiles**

  ```bash
  cd src/frontend && npx tsc --noEmit
  ```

  Expected: no errors.

- [ ] **Step 3: Commit**

  ```bash
  git add src/frontend/src/features/auth/api.ts
  git commit -m "feat(frontend): add postForgotPassword and postResetPassword API functions"
  ```

---

## Task 8: Frontend — Login page "forgot" mode

**Files:**
- Modify: `src/frontend/src/routes/login.tsx`

- [ ] **Step 1: Update the login page**

  Replace the full contents of `src/frontend/src/routes/login.tsx` with:

  ```tsx
  // src/frontend/src/routes/login.tsx
  import { createFileRoute, useNavigate } from '@tanstack/react-router'
  import { useState, useId } from 'react'
  import { CardArt } from '../components/design-system/CardArt'
  import { useAuthStore } from '../store/auth'
  import { postLogin, postSignup, getMe, postForgotPassword } from '../features/auth/api'
  import styles from './Login.module.css'

  export const Route = createFileRoute('/login')({
    component: LoginPage,
  })

  const CARD_NAMES = ['Ragavan', 'Mox Diamond', 'Sheoldred', 'One Ring']

  type Mode = 'login' | 'signup' | 'forgot'

  function LoginPage() {
    const [mode, setMode] = useState<Mode>('login')
    const [email, setEmail] = useState('')
    const [username, setUsername] = useState('')
    const [password, setPassword] = useState('')
    const [error, setError] = useState<string | null>(null)
    const [submitting, setSubmitting] = useState(false)
    const [resetSent, setResetSent] = useState(false)

    const navigate = useNavigate()
    const login = useAuthStore((s) => s.login)
    const formId = useId()

    function switchMode(next: Mode) {
      setMode(next)
      setError(null)
      setEmail('')
      setUsername('')
      setPassword('')
      setResetSent(false)
    }

    async function handleSubmit(e: React.FormEvent) {
      e.preventDefault()
      setError(null)
      setSubmitting(true)

      try {
        if (mode === 'forgot') {
          await postForgotPassword(email)
          setResetSent(true)
          return
        }

        if (mode === 'signup') {
          await postSignup({ username, email, password })
        }

        const tokens = await postLogin(email, password)
        const me = await getMe(tokens.access_token)
        login(tokens.access_token, { username: me.username, email })
        navigate({ to: '/' })
      } catch (err: unknown) {
        const e = err as { status?: number; message?: string }
        if (mode === 'signup' && e.status === 409) {
          setError('An account with that email or username already exists.')
        } else if (mode === 'signup' && e.status === 422) {
          setError('Please fill in all required fields correctly.')
        } else if (mode === 'login' && e.status === 401) {
          setError('Invalid email or password.')
        } else {
          setError(e.message ?? 'Something went wrong. Please try again.')
        }
      } finally {
        setSubmitting(false)
      }
    }

    const isLogin = mode === 'login'
    const isForgot = mode === 'forgot'

    const leftEyebrow = isLogin ? '● welcome back' : isForgot ? '● account recovery' : '● get started'
    const leftHeadline = isLogin ? (
      <>The market<br /><span className={styles.leftHeadlineAccent}>moves while you sleep.</span></>
    ) : isForgot ? (
      <>Reset your<br /><span className={styles.leftHeadlineAccent}>password.</span></>
    ) : (
      <>Track every card,<br /><span className={styles.leftHeadlineAccent}>every price move.</span></>
    )
    const leftSub = isLogin
      ? 'Sign in to see what your collection did overnight, manage active eBay listings, and catch every price swing.'
      : isForgot
      ? "Enter your email and we'll send you a link to reset your password."
      : 'Create your account and start tracking your MTG collection with real-time pricing and eBay integration.'

    return (
      <div className={styles.page}>
        {/* ── Left panel ── */}
        <div className={styles.left}>
          <div className={styles.leftGlow} />
          <div className={styles.leftLogo}>
            <div className={styles.logoMark}>a</div>
            <span className={styles.logoText}>
              auto<span className={styles.logoAccent}>mana</span>
            </span>
          </div>
          <div className={styles.leftContent}>
            <div className={styles.leftEyebrow}>{leftEyebrow}</div>
            <h1 className={styles.leftHeadline}>{leftHeadline}</h1>
            <p className={styles.leftSub}>{leftSub}</p>
          </div>
          <div className={styles.cardStack}>
            {CARD_NAMES.map((name, i) => (
              <div
                key={name}
                style={{
                  marginLeft: i === 0 ? 0 : -28,
                  transform: `rotate(${(i - 1.5) * 4}deg)`,
                }}
              >
                <CardArt name={name} w={100} h={140} hue={180 + i * 18} label={false} />
              </div>
            ))}
          </div>
        </div>

        {/* ── Right panel ── */}
        <div className={styles.right}>
          {isForgot ? (
            resetSent ? (
              <>
                <div className={styles.formTitle}>Check your inbox</div>
                <div className={styles.formSub}>
                  A reset link is on its way. It expires in 30 minutes.
                </div>
                <div style={{ marginTop: 24 }}>
                  <button
                    type="button"
                    className={styles.formSubLink}
                    onClick={() => switchMode('login')}
                  >
                    ← Back to log in
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className={styles.formTitle}>Reset password</div>
                <div className={styles.formSub}>
                  Remembered it?{' '}
                  <button
                    type="button"
                    className={styles.formSubLink}
                    onClick={() => switchMode('login')}
                  >
                    Log in
                  </button>
                </div>
                <form id={formId} onSubmit={handleSubmit} className={styles.fields} noValidate>
                  <div>
                    <label htmlFor={`${formId}-email`} className={styles.fieldLabel}>
                      Email
                    </label>
                    <input
                      id={`${formId}-email`}
                      className={styles.input}
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@example.com"
                      autoComplete="email"
                      required
                    />
                  </div>
                  {error && (
                    <div className={styles.errorBanner} role="alert">
                      {error}
                    </div>
                  )}
                  <button
                    type="submit"
                    className={styles.submitBtn}
                    disabled={submitting}
                    aria-busy={submitting}
                  >
                    {submitting ? 'Sending...' : 'Send reset link →'}
                  </button>
                </form>
              </>
            )
          ) : (
            <>
              <div className={styles.formTitle}>{isLogin ? 'Log in' : 'Create account'}</div>
              <div className={styles.formSub}>
                {isLogin ? (
                  <>
                    Don't have an account?{' '}
                    <button
                      type="button"
                      className={styles.formSubLink}
                      onClick={() => switchMode('signup')}
                    >
                      Create one
                    </button>
                  </>
                ) : (
                  <>
                    Already have an account?{' '}
                    <button
                      type="button"
                      className={styles.formSubLink}
                      onClick={() => switchMode('login')}
                    >
                      Log in
                    </button>
                  </>
                )}
              </div>

              <form
                id={formId}
                onSubmit={handleSubmit}
                className={styles.fields}
                noValidate
              >
                {!isLogin && (
                  <div>
                    <label htmlFor={`${formId}-username`} className={styles.fieldLabel}>
                      Username
                    </label>
                    <input
                      id={`${formId}-username`}
                      className={styles.input}
                      type="text"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      placeholder="yourname"
                      autoComplete="username"
                      required
                      minLength={3}
                      maxLength={50}
                    />
                  </div>
                )}

                <div>
                  <label htmlFor={`${formId}-email`} className={styles.fieldLabel}>
                    Email
                  </label>
                  <input
                    id={`${formId}-email`}
                    className={styles.input}
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    autoComplete="email"
                    required
                  />
                </div>

                <div>
                  <div className={styles.fieldHeader}>
                    <label htmlFor={`${formId}-password`} className={styles.fieldLabel}>
                      Password
                    </label>
                    {isLogin && (
                      <button
                        type="button"
                        className={styles.forgotLink}
                        onClick={() => switchMode('forgot')}
                      >
                        Forgot?
                      </button>
                    )}
                  </div>
                  <input
                    id={`${formId}-password`}
                    className={styles.input}
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    autoComplete={isLogin ? 'current-password' : 'new-password'}
                    required
                    minLength={8}
                  />
                </div>

                {error && (
                  <div className={styles.errorBanner} role="alert">
                    {error}
                  </div>
                )}

                <button
                  type="submit"
                  className={styles.submitBtn}
                  disabled={submitting}
                  aria-busy={submitting}
                >
                  {submitting
                    ? isLogin ? 'Logging in...' : 'Creating account...'
                    : isLogin ? 'Log in →' : 'Create account →'}
                </button>
              </form>

              <div className={styles.terms}>
                By continuing you agree to the Terms · Privacy
              </div>
            </>
          )}
        </div>
      </div>
    )
  }
  ```

- [ ] **Step 2: Verify TypeScript**

  ```bash
  cd src/frontend && npx tsc --noEmit
  ```

  Expected: no errors.

- [ ] **Step 3: Commit**

  ```bash
  git add src/frontend/src/routes/login.tsx
  git commit -m "feat(frontend): add forgot-password mode to login page"
  ```

---

## Task 9: Frontend — `/reset-password` route + PUBLIC_PATHS

**Files:**
- Create: `src/frontend/src/routes/reset-password.tsx`
- Modify: `src/frontend/src/routes/__root.tsx`

- [ ] **Step 1: Add `/reset-password` to PUBLIC_PATHS**

  Open `src/frontend/src/routes/__root.tsx`. Find:

  ```typescript
  const PUBLIC_PATHS = ['/login', '/search']
  ```

  Replace with:

  ```typescript
  const PUBLIC_PATHS = ['/login', '/search', '/reset-password']
  ```

- [ ] **Step 2: Create the reset-password route**

  Create `src/frontend/src/routes/reset-password.tsx`:

  ```tsx
  // src/frontend/src/routes/reset-password.tsx
  import { createFileRoute, useNavigate, useSearch } from '@tanstack/react-router'
  import { useState, useId } from 'react'
  import { z } from 'zod'
  import { CardArt } from '../components/design-system/CardArt'
  import { postResetPassword } from '../features/auth/api'
  import styles from './Login.module.css'

  const searchSchema = z.object({
    token: z.string().optional(),
  })

  export const Route = createFileRoute('/reset-password')({
    validateSearch: searchSchema,
    component: ResetPasswordPage,
  })

  const CARD_NAMES = ['Ragavan', 'Mox Diamond', 'Sheoldred', 'One Ring']

  function ResetPasswordPage() {
    const { token } = useSearch({ from: '/reset-password' })
    const navigate = useNavigate()
    const formId = useId()

    const [newPassword, setNewPassword] = useState('')
    const [confirmPassword, setConfirmPassword] = useState('')
    const [error, setError] = useState<string | null>(null)
    const [submitting, setSubmitting] = useState(false)
    const [success, setSuccess] = useState(false)

    if (!token) {
      return (
        <div className={styles.page}>
          <div className={styles.left}>
            <div className={styles.leftGlow} />
            <div className={styles.leftLogo}>
              <div className={styles.logoMark}>a</div>
              <span className={styles.logoText}>
                auto<span className={styles.logoAccent}>mana</span>
              </span>
            </div>
            <div className={styles.leftContent}>
              <div className={styles.leftEyebrow}>● account recovery</div>
              <h1 className={styles.leftHeadline}>
                Reset your<br />
                <span className={styles.leftHeadlineAccent}>password.</span>
              </h1>
            </div>
            <div className={styles.cardStack}>
              {CARD_NAMES.map((name, i) => (
                <div
                  key={name}
                  style={{ marginLeft: i === 0 ? 0 : -28, transform: `rotate(${(i - 1.5) * 4}deg)` }}
                >
                  <CardArt name={name} w={100} h={140} hue={180 + i * 18} label={false} />
                </div>
              ))}
            </div>
          </div>
          <div className={styles.right}>
            <div className={styles.formTitle}>Invalid link</div>
            <div className={styles.formSub}>
              This reset link is missing or malformed.{' '}
              <button
                type="button"
                className={styles.formSubLink}
                onClick={() => navigate({ to: '/login' })}
              >
                Request a new one
              </button>
            </div>
          </div>
        </div>
      )
    }

    async function handleSubmit(e: React.FormEvent) {
      e.preventDefault()
      setError(null)

      if (newPassword !== confirmPassword) {
        setError('Passwords do not match.')
        return
      }

      setSubmitting(true)
      try {
        await postResetPassword(token, newPassword)
        setSuccess(true)
        setTimeout(() => navigate({ to: '/login' }), 2000)
      } catch (err: unknown) {
        const e = err as { status?: number; message?: string }
        if (e.status === 400) {
          setError('This link has expired or has already been used.')
        } else {
          setError(e.message ?? 'Something went wrong. Please try again.')
        }
      } finally {
        setSubmitting(false)
      }
    }

    return (
      <div className={styles.page}>
        {/* ── Left panel ── */}
        <div className={styles.left}>
          <div className={styles.leftGlow} />
          <div className={styles.leftLogo}>
            <div className={styles.logoMark}>a</div>
            <span className={styles.logoText}>
              auto<span className={styles.logoAccent}>mana</span>
            </span>
          </div>
          <div className={styles.leftContent}>
            <div className={styles.leftEyebrow}>● account recovery</div>
            <h1 className={styles.leftHeadline}>
              Reset your<br />
              <span className={styles.leftHeadlineAccent}>password.</span>
            </h1>
            <p className={styles.leftSub}>Choose a new password for your AutoMana account.</p>
          </div>
          <div className={styles.cardStack}>
            {CARD_NAMES.map((name, i) => (
              <div
                key={name}
                style={{ marginLeft: i === 0 ? 0 : -28, transform: `rotate(${(i - 1.5) * 4}deg)` }}
              >
                <CardArt name={name} w={100} h={140} hue={180 + i * 18} label={false} />
              </div>
            ))}
          </div>
        </div>

        {/* ── Right panel ── */}
        <div className={styles.right}>
          {success ? (
            <>
              <div className={styles.formTitle}>Password updated</div>
              <div className={styles.formSub}>Redirecting you to the login page…</div>
            </>
          ) : (
            <>
              <div className={styles.formTitle}>Set new password</div>
              <div className={styles.formSub}>
                Remembered it?{' '}
                <button
                  type="button"
                  className={styles.formSubLink}
                  onClick={() => navigate({ to: '/login' })}
                >
                  Log in
                </button>
              </div>
              <form id={formId} onSubmit={handleSubmit} className={styles.fields} noValidate>
                <div>
                  <label htmlFor={`${formId}-new`} className={styles.fieldLabel}>
                    New password
                  </label>
                  <input
                    id={`${formId}-new`}
                    className={styles.input}
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="••••••••"
                    autoComplete="new-password"
                    required
                    minLength={8}
                  />
                </div>
                <div>
                  <label htmlFor={`${formId}-confirm`} className={styles.fieldLabel}>
                    Confirm password
                  </label>
                  <input
                    id={`${formId}-confirm`}
                    className={styles.input}
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="••••••••"
                    autoComplete="new-password"
                    required
                    minLength={8}
                  />
                </div>
                {error && (
                  <div className={styles.errorBanner} role="alert">
                    {error}
                  </div>
                )}
                <button
                  type="submit"
                  className={styles.submitBtn}
                  disabled={submitting}
                  aria-busy={submitting}
                >
                  {submitting ? 'Saving...' : 'Set new password →'}
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    )
  }
  ```

- [ ] **Step 3: Regenerate the TanStack Router route tree**

  TanStack Router auto-generates `routeTree.gen.ts` from the files in `src/routes/`. Run:

  ```bash
  cd src/frontend && npx tsr generate
  ```

  Expected: `routeTree.gen.ts` updated — the file now imports `ResetPasswordRouteImport` from `./routes/reset-password`.

- [ ] **Step 4: Verify TypeScript**

  ```bash
  cd src/frontend && npx tsc --noEmit
  ```

  Expected: no errors.

- [ ] **Step 5: Run frontend tests**

  ```bash
  cd src/frontend && npm test
  ```

  Expected: all existing tests pass (no regressions).

- [ ] **Step 6: Commit**

  ```bash
  git add src/frontend/src/routes/reset-password.tsx \
          src/frontend/src/routes/__root.tsx \
          src/frontend/src/routeTree.gen.ts
  git commit -m "feat(frontend): add /reset-password route and wire Forgot? link"
  ```

---

## Done

All 9 tasks complete. The flow is:

1. User clicks **Forgot?** on the login page → enters email → sees "Check your inbox" confirmation.
2. Resend delivers an email with `{APP_BASE_URL}/reset-password?token=<raw_token>`.
3. User lands on `/reset-password?token=...` → enters new password twice → submits.
4. Backend validates token hash, updates password, invalidates all sessions, marks token used.
5. User is redirected to `/login` after 2 seconds and logs in with the new password.
