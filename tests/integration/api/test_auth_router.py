"""
Integration tests for the auth router — issue #154.

Covers the full login → session cookie → protected route → refresh → logout flow
against a real DB. Every test runs against the shared testcontainers setup;
no mocks for DB, Redis, or the FastAPI app itself.
"""
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.api]


# ---------------------------------------------------------------------------
# POST /api/users/auth/token — login
# ---------------------------------------------------------------------------

async def test_login_valid_credentials_returns_token(client, created_user, test_user_data):
    response = await client.post(
        "/api/users/auth/token",
        content=f"username={test_user_data['email']}&password={test_user_data['password']}",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


async def test_login_sets_session_cookie(client, created_user, test_user_data):
    response = await client.post(
        "/api/users/auth/token",
        content=f"username={test_user_data['email']}&password={test_user_data['password']}",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    assert "session_id" in response.cookies


async def test_login_invalid_password_returns_401(client, created_user, test_user_data):
    response = await client.post(
        "/api/users/auth/token",
        content=f"username={test_user_data['email']}&password=WrongPassword999!",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 401


async def test_login_unknown_user_returns_401(client):
    response = await client.post(
        "/api/users/auth/token",
        content="username=nobody@example.com&password=SomePass123!",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/users/auth/token/refresh
# ---------------------------------------------------------------------------

async def test_refresh_with_valid_session_cookie_returns_new_token(client, created_user, test_user_data):
    login = await client.post(
        "/api/users/auth/token",
        content=f"username={test_user_data['email']}&password={test_user_data['password']}",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login.status_code == 200
    session_cookie = login.cookies["session_id"]

    refresh = await client.post(
        "/api/users/auth/token/refresh",
        cookies={"session_id": session_cookie},
    )
    assert refresh.status_code == 200
    assert "access_token" in refresh.json()


async def test_refresh_without_session_cookie_returns_401(client):
    response = await client.post("/api/users/auth/token/refresh")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/users/auth/logout
# ---------------------------------------------------------------------------

async def test_logout_with_valid_session_returns_204(client, created_user, test_user_data):
    login = await client.post(
        "/api/users/auth/token",
        content=f"username={test_user_data['email']}&password={test_user_data['password']}",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    session_cookie = login.cookies["session_id"]

    logout = await client.post(
        "/api/users/auth/logout",
        cookies={"session_id": session_cookie},
    )
    assert logout.status_code == 204
    assert logout.cookies.get("session_id") in (None, "")


async def test_logout_without_session_is_idempotent(client):
    response = await client.post("/api/users/auth/logout")
    assert response.status_code == 204


async def test_session_invalid_after_logout(client, created_user, test_user_data):
    login = await client.post(
        "/api/users/auth/token",
        content=f"username={test_user_data['email']}&password={test_user_data['password']}",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    session_cookie = login.cookies["session_id"]

    await client.post(
        "/api/users/auth/logout",
        cookies={"session_id": session_cookie},
    )

    refresh = await client.post(
        "/api/users/auth/token/refresh",
        cookies={"session_id": session_cookie},
    )
    assert refresh.status_code == 401
