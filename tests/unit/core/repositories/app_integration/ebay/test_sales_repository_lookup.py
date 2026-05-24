"""Unit test: EbaySalesRepository.get_ebay_card_lookup delegates to execute_query."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

pytestmark = pytest.mark.asyncio


async def test_get_ebay_card_lookup_returns_dicts():
    from automana.core.repositories.app_integration.ebay.sales_repository import (
        EbaySalesRepository,
    )
    from automana.core.repositories.app_integration.ebay import sales_queries

    mock_conn = AsyncMock()
    repo = EbaySalesRepository(mock_conn)

    fake_rows = [
        {"source_product_id": 1, "card_name": "Sheoldred, the Apocalypse",
         "set_code": "DMU", "source_code": "ebay"},
        {"source_product_id": 2, "card_name": "Atraxa, Praetors' Voice",
         "set_code": "ONE", "source_code": "ebay"},
    ]

    with patch.object(repo, "execute_query", return_value=fake_rows) as mock_eq:
        result = await repo.get_ebay_card_lookup()

    mock_eq.assert_called_once_with(sales_queries.GET_EBAY_CARD_LOOKUP, ())
    assert len(result) == 2
    assert result[0]["card_name"] == "Sheoldred, the Apocalypse"
    assert result[1]["set_code"] == "ONE"
