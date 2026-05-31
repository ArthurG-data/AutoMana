import pytest

pytestmark = [pytest.mark.integration, pytest.mark.api]


@pytest.mark.asyncio
async def test_public_list_excludes_drafts(client, auth_headers):
    # create (draft) via admin
    create = await client.post("/api/content/articles/admin/",
                               headers=auth_headers,
                               json={"title": "Draft Piece", "body_markdown": "hello"})
    assert create.status_code == 201
    # public list should not contain the draft
    pub = await client.get("/api/content/articles/")
    assert pub.status_code == 200
    slugs = [a["slug"] for a in pub.json()["data"]]
    assert "draft-piece" not in slugs


@pytest.mark.asyncio
async def test_public_get_draft_returns_404(client, auth_headers):
    await client.post("/api/content/articles/admin/", headers=auth_headers,
                      json={"title": "Secret", "body_markdown": "x"})
    resp = await client.get("/api/content/articles/secret")
    assert resp.status_code == 404  # draft not visible publicly -> mapped to 404


@pytest.mark.asyncio
async def test_publish_then_public_list_includes_article(client, auth_headers):
    create = await client.post("/api/content/articles/admin/", headers=auth_headers,
                               json={"title": "Live Read", "body_markdown": "word " * 240,
                                     "tags": ["Standard"]})
    assert create.status_code == 201
    article_id = create.json()["data"]["article_id"]

    publish = await client.post(f"/api/content/articles/admin/{article_id}/publish?published=true",
                                headers=auth_headers)
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
