"""
Tests for automana.api.services.user_management.user_service.register

Regression test for the HTTPException passthrough bug:
- user_service.register had a broad `except Exception` that re-wrapped HTTPException
  as UserError, causing 409 Conflict responses to become 500 Internal Server Error.
- Fix: add `except HTTPException: raise` before the broad handler.
"""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException

from automana.api.services.user_management import user_service
from automana.api.schemas.user_management.user import BaseUser
from automana.core.exceptions.service_layer_exceptions.user_management import user_exceptions

pytestmark = pytest.mark.unit


def _make_user() -> BaseUser:
    return BaseUser(
        username="alice",
        email="alice@example.com",
        fullname="Alice Example",
        password="plaintext-for-test",
    )


class TestRegisterHTTPExceptionPassthrough:
    """HTTPException (e.g. 409 Conflict) must propagate unchanged from register()."""

    async def test_http_exception_is_not_swallowed_by_broad_handler(
        self, mock_user_repository
    ):
        """When the repository raises an HTTPException it must not be re-wrapped as UserError."""
        conflict = HTTPException(status_code=409, detail="Username already exists")
        mock_user_repository.add = AsyncMock(side_effect=conflict)

        with pytest.raises(HTTPException) as exc_info:
            await user_service.register(
                user_repository=mock_user_repository,
                user=_make_user(),
            )

        assert exc_info.value.status_code == 409, (
            f"Expected 409, got {exc_info.value.status_code} — "
            "HTTPException was re-wrapped by the broad except handler"
        )

    async def test_http_exception_detail_is_preserved(self, mock_user_repository):
        """The original detail message on the HTTPException must survive passthrough."""
        detail = "Email already registered"
        mock_user_repository.add = AsyncMock(
            side_effect=HTTPException(status_code=409, detail=detail)
        )

        with pytest.raises(HTTPException) as exc_info:
            await user_service.register(
                user_repository=mock_user_repository,
                user=_make_user(),
            )

        assert exc_info.value.detail == detail

    async def test_non_http_exception_still_raises_user_error(
        self, mock_user_repository
    ):
        """Generic exceptions must still be wrapped as UserError (existing behavior)."""
        mock_user_repository.add = AsyncMock(
            side_effect=RuntimeError("connection refused")
        )

        with pytest.raises(user_exceptions.UserError):
            await user_service.register(
                user_repository=mock_user_repository,
                user=_make_user(),
            )
