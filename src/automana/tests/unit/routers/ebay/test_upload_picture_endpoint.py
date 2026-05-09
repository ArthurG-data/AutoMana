import io
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from automana.api.dependancies.auth.users import get_current_active_user
from automana.api.dependancies.service_deps import get_service_manager
from automana.api.routers.integrations.ebay.ebay_selling import ebay_listing_router

app = FastAPI()
app.include_router(ebay_listing_router)


def make_fake_user():
    user = MagicMock()
    user.unique_id = "00000000-0000-0000-0000-000000000001"
    return user


def make_mock_service_manager(return_value=None):
    mock_sm = MagicMock()
    mock_sm.execute_service = AsyncMock(return_value=return_value or {})
    return mock_sm


def test_upload_picture_returns_url():
    fake_user = make_fake_user()
    mock_sm = make_mock_service_manager(return_value={"url": "https://i.ebayimg.com/img.jpg"})

    app.dependency_overrides[get_current_active_user] = lambda: fake_user
    app.dependency_overrides[get_service_manager] = lambda: mock_sm
    try:
        client = TestClient(app)
        response = client.post(
            "/listing/upload-picture?app_code=automana_au",
            files={"file": ("test.jpg", io.BytesIO(b"fake"), "image/jpeg")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["data"]["url"] == "https://i.ebayimg.com/img.jpg"


def test_upload_picture_rejects_non_image():
    fake_user = make_fake_user()
    mock_sm = make_mock_service_manager()

    app.dependency_overrides[get_current_active_user] = lambda: fake_user
    app.dependency_overrides[get_service_manager] = lambda: mock_sm
    try:
        client = TestClient(app)
        response = client.post(
            "/listing/upload-picture?app_code=automana_au",
            files={"file": ("doc.pdf", io.BytesIO(b"fake"), "application/pdf")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "image" in response.json()["detail"].lower()
