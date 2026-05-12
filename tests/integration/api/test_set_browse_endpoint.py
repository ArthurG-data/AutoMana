import pytest


@pytest.mark.asyncio
async def test_browse_returns_200_with_expected_shape(client):
    response = await client.get("/api/catalog/mtg/set-reference/browse")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)
    if body["data"]:
        item = body["data"][0]
        assert "set_code" in item
        assert "set_name" in item
        assert "set_type" in item
        assert "card_count" in item
        assert "released_at" in item
        assert "icon_svg_uri" in item
        assert "key_art_uri" in item


@pytest.mark.asyncio
async def test_browse_key_art_uri_is_string_or_null(client):
    response = await client.get("/api/catalog/mtg/set-reference/browse")
    assert response.status_code == 200
    sets = response.json()["data"]
    for item in sets:
        assert item["key_art_uri"] is None or isinstance(item["key_art_uri"], str)


@pytest.mark.asyncio
async def test_browse_includes_parent_set_code(client):
    response = await client.get("/api/catalog/mtg/set-reference/browse")
    assert response.status_code == 200
    sets = response.json()["data"]
    assert len(sets) > 0
    for item in sets:
        assert "parent_set_code" in item
        assert item["parent_set_code"] is None or isinstance(item["parent_set_code"], str)
    child_sets = [s for s in sets if s["parent_set_code"] is not None]
    assert len(child_sets) > 0, "Expected at least one child set with a non-null parent_set_code"


@pytest.mark.asyncio
async def test_browse_excludes_digital_sets(client):
    response = await client.get("/api/catalog/mtg/set-reference/browse")
    assert response.status_code == 200
    sets = response.json()["data"]
    digital_codes = {"tic", "ana", "anb"}
    returned_codes = {s["set_code"] for s in sets}
    assert returned_codes.isdisjoint(digital_codes), (
        f"Digital sets found in browse response: {returned_codes & digital_codes}"
    )
