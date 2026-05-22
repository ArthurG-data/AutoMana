"""
Fixtures for API integration tests.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def test_user_data():
    """Provides test user credentials."""
    return {
        "username": f"test_user_{uuid.uuid4().hex[:8]}",
        "email": f"test_{uuid.uuid4().hex[:8]}@example.com",
        "password": "TestPassword123!",
    }


@pytest_asyncio.fixture
async def created_user(client, test_user_data):
    """Creates a test user via the API and returns the user object."""
    response = await client.post(
        "/api/users/",
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
    """Generates a Bearer token for the test user using the same JWT settings as the app."""
    from automana.api.services.auth.auth import create_access_token
    from automana.core.settings import get_settings

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
    Creates a collection with multiple seeded entries for pagination testing.
    Uses known MTG card identifiers (set_code + collector_number) to populate the collection.
    Returns dict with collection_id and entry_ids.

    Requires a running database with card catalog data loaded.
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

    # Attempt to add entries using common MTG card identifiers.
    # Using basic cards that are likely to exist in any standard Scryfall dataset.
    # Format: (set_code, collector_number)
    test_cards = [
        ("dom", "1"),      # Plains from Dominaria
        ("dom", "2"),      # Island from Dominaria
        ("dom", "3"),      # Swamp from Dominaria
        ("dom", "4"),      # Mountain from Dominaria
        ("dom", "5"),      # Forest from Dominaria
        ("m19", "1"),      # Plains from M19
        ("m19", "2"),      # Island from M19
        ("m19", "3"),      # Swamp from M19
        ("m19", "4"),      # Mountain from M19
        ("m19", "5"),      # Forest from M19
        ("m20", "1"),      # Plains from M20
        ("m20", "2"),      # Island from M20
    ]

    entry_ids = []
    for set_code, collector_number in test_cards:
        entry_response = await client.post(
            f"/api/catalog/mtg/collection/{collection_id}/entries",
            headers=auth_headers,
            json={
                "set_code": set_code,
                "collector_number": collector_number,
                "purchase_price": "10.00",
                "condition": "NM",
                "finish": "NONFOIL",
            },
        )

        # If adding entries fails, it means either:
        # 1. The card data doesn't exist in the database (cards not loaded yet)
        # 2. There's an issue with the database connection
        # In either case, skip the fixture to avoid vacuous test passes.
        if entry_response.status_code != 201:
            pytest.skip(
                f"seeded_collection fixture skipped: failed to add test cards to collection. "
                f"Card {set_code}/{collector_number} returned status {entry_response.status_code}. "
                f"This fixture requires a running database with card catalog data loaded."
            )

        entry_data = entry_response.json().get("data")
        entry_ids.append(entry_data["item_id"])

    return {
        "collection_id": collection_id,
        "collection_name": collection_data["collection_name"],
        "entry_ids": entry_ids,
    }
