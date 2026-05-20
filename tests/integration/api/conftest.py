"""
Fixtures for API integration tests.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio

from automana.api.services.auth.auth import create_access_token
from automana.core.settings import get_settings


@pytest_asyncio.fixture
async def test_user_data():
    """Provides test user credentials."""
    return {
        "username": f"test_user_{uuid.uuid4().hex[:8]}",
        "email": f"test_{uuid.uuid4().hex[:8]}@test.local",
        "password": "TestPassword123!",
    }


@pytest_asyncio.fixture
async def created_user(client, test_user_data):
    """Creates a test user via the API and returns the user object."""
    # Register the user
    response = await client.post(
        "/api/users/auth/register",
        json={
            "username": test_user_data["username"],
            "email": test_user_data["email"],
            "password": test_user_data["password"],
        },
    )
    assert response.status_code == 201, f"User creation failed: {response.text}"
    user = response.json().get("data")
    assert user is not None
    return user


@pytest_asyncio.fixture
async def auth_headers(created_user, test_user_data):
    """
    Generates a Bearer token for the test user.
    Uses the same JWT settings as the app.
    """
    settings = get_settings()
    token = create_access_token(
        data={"sub": created_user["username"]},
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        expires_delta=timedelta(minutes=30),
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def seeded_collection(client, auth_headers, created_user):
    """
    Creates a collection with multiple entries (seeded with test data).
    Returns dict with collection_id and entry_ids.
    """
    # Create a collection
    collection_response = await client.post(
        "/api/catalog/mtg/collection",
        headers=auth_headers,
        json={"collection_name": "Test Collection", "description": "Test collection for pagination"},
    )
    assert collection_response.status_code == 201, f"Collection creation failed: {collection_response.text}"
    collection_data = collection_response.json().get("data")
    collection_id = collection_data["collection_id"]

    # For now, return the collection with an empty list of entries.
    # If seeded entries are needed, they would be added here by calling
    # the add_entry endpoint. This fixture will be extended when test data
    # seeding is implemented.
    return {
        "collection_id": collection_id,
        "collection_name": collection_data["collection_name"],
        "entry_ids": [],
    }
