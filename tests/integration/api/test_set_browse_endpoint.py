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
