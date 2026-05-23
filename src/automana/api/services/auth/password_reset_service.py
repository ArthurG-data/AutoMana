import hashlib
import logging
import secrets
from datetime import datetime, timezone, timedelta

from automana.api.repositories.auth.password_reset_repository import PasswordResetRepository
from automana.api.repositories.auth.session_repository import SessionRepository
from automana.api.repositories.user_management.user_repository import UserRepository
from automana.api.services.auth.auth import get_hash_password
from automana.api.services.email.email_service import EmailService
from automana.core.exceptions.service_layer_exceptions.user_management.user_exceptions import InvalidResetTokenError
from automana.core.framework.registry import ServiceRegistry

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
        raise InvalidResetTokenError(_INVALID_MSG)
    if row["used_at"] is not None:
        raise InvalidResetTokenError(_INVALID_MSG)
    if row["expires_at"] < datetime.now(timezone.utc):
        raise InvalidResetTokenError(_INVALID_MSG)

    hashed = get_hash_password(new_password)
    await user_repository.update_password(user_id=row["user_id"], hashed_password=hashed)
    await password_reset_repository.mark_used(row["id"])
    await session_repository.invalidate_all_for_user(row["user_id"])

    logger.info("password_reset_complete", extra={"user_id": str(row["user_id"])})
    return {"status": "ok"}
