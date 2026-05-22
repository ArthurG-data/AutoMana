"""
Integration tests for the users router — issue #155.

Covers the full register → read → update → delete lifecycle through
the real DB. Also exercises the admin-only list endpoint.
"""
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.api]


# ---------------------------------------------------------------------------
# POST /api/users/ — register
# ---------------------------------------------------------------------------

async def test_register_new_user_returns_201(client, test_user_data):
    response = await client.post("/api/users/", json={
        "username": test_user_data["username"],
        "email": test_user_data["email"],
        "password": test_user_data["password"],
    })
    assert response.status_code == 201
    user = response.json()["data"]
    assert user["username"] == test_user_data["username"]
    assert user["email"] == test_user_data["email"]
    assert "hashed_password" not in user


async def test_register_duplicate_username_returns_409(client, created_user, test_user_data):
    response = await client.post("/api/users/", json={
        "username": test_user_data["username"],
        "email": f"other_{test_user_data['email']}",
        "password": test_user_data["password"],
    })
    assert response.status_code == 409


async def test_register_duplicate_email_returns_409(client, created_user, test_user_data):
    response = await client.post("/api/users/", json={
        "username": f"other_{test_user_data['username']}",
        "email": test_user_data["email"],
        "password": test_user_data["password"],
    })
    assert response.status_code == 409


async def test_register_invalid_email_returns_422(client):
    response = await client.post("/api/users/", json={
        "username": "validuser",
        "email": "not-an-email",
        "password": "SomePass123!",
    })
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/users/me — get current user
# ---------------------------------------------------------------------------

async def test_get_me_with_valid_token_returns_user(client, created_user, auth_headers):
    response = await client.get("/api/users/me", headers=auth_headers)
    assert response.status_code == 200
    user = response.json()
    assert user["username"] == created_user["username"]
    assert "hashed_password" not in user


async def test_get_me_without_auth_returns_401(client):
    response = await client.get("/api/users/me")
    assert response.status_code == 401


async def test_get_me_with_invalid_token_returns_401(client):
    response = await client.get(
        "/api/users/me",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# PUT /api/users/ — update current user
# ---------------------------------------------------------------------------

async def test_update_user_fullname_returns_200(client, created_user, auth_headers):
    response = await client.put(
        "/api/users/",
        headers=auth_headers,
        json={"fullname": "Updated Name"},
    )
    assert response.status_code == 200


async def test_update_user_without_auth_returns_401(client):
    response = await client.put(
        "/api/users/",
        json={"fullname": "No Auth"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/users/ — list users (admin-only)
# ---------------------------------------------------------------------------

async def test_list_users_without_auth_returns_401(client):
    response = await client.get("/api/users/")
    assert response.status_code == 401


async def test_list_users_as_regular_user_returns_403(client, created_user, auth_headers):
    response = await client.get("/api/users/", headers=auth_headers)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/users/{user_id} — delete user (admin-only)
# ---------------------------------------------------------------------------

async def test_delete_user_as_regular_user_returns_403(client, created_user, auth_headers):
    response = await client.delete(
        f"/api/users/{created_user['unique_id']}",
        headers=auth_headers,
    )
    assert response.status_code == 403


async def test_delete_user_without_auth_returns_401(client, created_user):
    response = await client.delete(f"/api/users/{created_user['unique_id']}")
    assert response.status_code == 401
