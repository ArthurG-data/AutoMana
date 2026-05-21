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
