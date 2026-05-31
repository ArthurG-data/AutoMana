from types import SimpleNamespace
from uuid import UUID

import pytest
import pytest_asyncio

pytestmark = [pytest.mark.integration, pytest.mark.api]


@pytest_asyncio.fixture
async def as_admin(test_app, created_user):
    """Override the admin gate so the created user can author articles.

    Returns the real user (its unique_id satisfies the article.author_id FK).
    The non-admin 403 path is exercised separately in
    test_non_admin_cannot_create.

    NOTE: the automana import is deferred inside the fixture (not at module
    level) — top-level automana imports freeze get_settings() before the
    test env overrides are applied (see tests/integration/conftest.py).
    """
    from automana.api.dependancies.auth.users import require_admin

    user = SimpleNamespace(
        unique_id=UUID(created_user["unique_id"]),
        username=created_user["username"],
    )
    test_app.dependency_overrides[require_admin] = lambda: user
    yield user
    test_app.dependency_overrides.pop(require_admin, None)


@pytest.mark.asyncio
async def test_non_admin_cannot_create(client, auth_headers):
    # A plain authenticated (non-admin) user must be forbidden from authoring.
    resp = await client.post("/api/content/articles/admin/", headers=auth_headers,
                             json={"title": "Sneaky", "body_markdown": "x"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_public_list_excludes_drafts(client, as_admin):
    create = await client.post("/api/content/articles/admin/",
                               json={"title": "Draft Piece", "body_markdown": "hello"})
    assert create.status_code == 201
    pub = await client.get("/api/content/articles/")
    assert pub.status_code == 200
    slugs = [a["slug"] for a in pub.json()["data"]]
    assert "draft-piece" not in slugs


@pytest.mark.asyncio
async def test_public_get_draft_returns_404(client, as_admin):
    await client.post("/api/content/articles/admin/",
                      json={"title": "Secret", "body_markdown": "x"})
    resp = await client.get("/api/content/articles/secret")
    assert resp.status_code == 404  # draft not visible publicly -> mapped to 404


@pytest.mark.asyncio
async def test_publish_then_public_list_includes_article(client, as_admin):
    create = await client.post("/api/content/articles/admin/",
                               json={"title": "Live Read", "body_markdown": "word " * 240,
                                     "tags": ["Standard"]})
    assert create.status_code == 201
    article_id = create.json()["data"]["article_id"]

    publish = await client.post(f"/api/content/articles/admin/{article_id}/publish?published=true")
    assert publish.status_code == 200
    assert publish.json()["data"]["status"] == "published"

    pub = await client.get("/api/content/articles/")
    slugs = [a["slug"] for a in pub.json()["data"]]
    assert "live-read" in slugs

    detail = await client.get("/api/content/articles/live-read")
    assert detail.status_code == 200
    body = detail.json()["data"]
    assert body["title"] == "Live Read"
    assert body["read_minutes"] == 1  # 240 words / 230 wpm -> rounds to 1
