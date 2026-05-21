import json
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_search_cards_returns_list():
    from automana.core.services.ai.agent_tools import TOOL_MAP, TOOL_SCHEMAS
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[
        {"card_name": "Lightning Bolt", "set_code": "LEA", "oracle_id": "abc"},
    ])
    result = json.loads(await TOOL_MAP["search_cards"](conn, query="lightning bolt"))
    assert isinstance(result, list)
    assert result[0]["card_name"] == "Lightning Bolt"


@pytest.mark.asyncio
async def test_get_card_prices_returns_list():
    from automana.core.services.ai.agent_tools import TOOL_MAP
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[
        {"card_name": "Lightning Bolt", "price_usd": "1.50", "source": "tcgplayer"},
    ])
    result = json.loads(await TOOL_MAP["get_card_prices"](conn, card_name="Lightning Bolt"))
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_stub_tools_return_not_implemented():
    from automana.core.services.ai.agent_tools import TOOL_MAP
    conn = AsyncMock()
    result = json.loads(await TOOL_MAP["get_listings_needing_action"](conn))
    assert result["status"] == "not_implemented"
    result2 = json.loads(await TOOL_MAP["get_card_buy_recommendations"](conn))
    assert result2["status"] == "not_implemented"


def test_tool_schemas_are_valid():
    from automana.core.services.ai.agent_tools import TOOL_SCHEMAS
    assert len(TOOL_SCHEMAS) == 8  # 6 active + 2 stubs
    names = {t["function"]["name"] for t in TOOL_SCHEMAS}
    expected = {
        "search_cards", "get_card_prices", "get_collection_summary",
        "get_active_listings", "get_sold_orders", "get_market_comps",
        "get_listings_needing_action", "get_card_buy_recommendations",
    }
    assert names == expected
