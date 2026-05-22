import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta, timezone
import httpx
from automana.core.repositories.app_integration.ebay.ApiFinding_repository import (
    EbayFindingAPIRepository,
    _parse_finding_items,
)

SAMPLE_FINDING_RESPONSE = {
    "findCompletedItemsResponse": [
        {
            "ack": ["Success"],
            "searchResult": [
                {
                    "count": "2",
                    "item": [
                        {
                            "itemId": ["111111"],
                            "title": ["Sheoldred the Apocalypse NM DMR MTG"],
                            "sellingStatus": [
                                {
                                    "currentPrice": [
                                        {"currencyId": "AUD", "__value__": "45.00"}
                                    ],
                                    "sellingState": ["EndedWithSales"],
                                }
                            ],
                            "listingInfo": [{"endTime": ["2026-01-01T10:00:00.000Z"]}],
                            "condition": [{"conditionDisplayName": ["Very Good"]}],
                            "viewItemURL": ["https://www.ebay.com.au/itm/111111"],
                        },
                        {
                            "itemId": ["222222"],
                            "title": ["Sheoldred Apocalypse LP MTG"],
                            "sellingStatus": [
                                {
                                    "currentPrice": [
                                        {"currencyId": "AUD", "__value__": "38.00"}
                                    ],
                                    "sellingState": ["EndedWithSales"],
                                }
                            ],
                            "listingInfo": [{"endTime": ["2026-01-02T10:00:00.000Z"]}],
                            "condition": [{"conditionDisplayName": ["Good"]}],
                            "viewItemURL": ["https://www.ebay.com.au/itm/222222"],
                        },
                    ],
                }
            ],
        }
    ]
}


def test_parse_finding_items_extracts_two_items():
    items = _parse_finding_items(SAMPLE_FINDING_RESPONSE)
    assert len(items) == 2


def test_parse_finding_items_first_item_fields():
    items = _parse_finding_items(SAMPLE_FINDING_RESPONSE)
    first = items[0]
    assert first["item_id"] == "111111"
    assert first["title"] == "Sheoldred the Apocalypse NM DMR MTG"
    assert first["price"] == 45.0
    assert first["currency"] == "AUD"
    assert first["condition"] == "Very Good"
    assert first["url"] == "https://www.ebay.com.au/itm/111111"
    assert first["sold_date"] == "2026-01-01T10:00:00.000Z"


def test_parse_finding_items_empty_response():
    empty = {"findCompletedItemsResponse": [{"ack": ["Success"], "searchResult": [{"count": "0"}]}]}
    items = _parse_finding_items(empty)
    assert items == []


def test_finding_repository_name():
    repo = EbayFindingAPIRepository(environment="sandbox")
    assert repo.name == "EbayFindingAPIRepository"


@pytest.mark.asyncio
async def test_find_completed_items_builds_correct_params():
    repo = EbayFindingAPIRepository(environment="sandbox")
    min_date = datetime(2026, 1, 1, tzinfo=timezone.utc)

    captured_params = {}

    async def fake_send(method, endpoint, *, params=None, headers=None, **kwargs):
        captured_params.update(params or {})
        mock_resp = MagicMock()
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {
            "findCompletedItemsResponse": [{"ack": ["Success"], "searchResult": [{"count": "0"}]}]
        }
        return mock_resp

    with patch.object(repo, "send", side_effect=fake_send):
        with patch.object(repo, "_parse_response", return_value={
            "findCompletedItemsResponse": [{"ack": ["Success"], "searchResult": [{"count": "0"}]}]
        }):
            await repo.find_completed_items(
                keywords="Sheoldred DMR MTG",
                app_id="TESTAPP-ID",
                category_id=2536,
                condition_id=3000,
                min_date=min_date,
                limit=25,
            )

    assert captured_params.get("OPERATION-NAME") == "findCompletedItems"
    assert captured_params.get("SECURITY-APPNAME") == "TESTAPP-ID"
    assert captured_params.get("keywords") == "Sheoldred DMR MTG"
    assert captured_params.get("RESPONSE-DATA-FORMAT") == "JSON"
    assert "paginationInput.entriesPerPage" in captured_params


@pytest.mark.asyncio
async def test_find_completed_items_passes_global_id_to_params():
    repo = EbayFindingAPIRepository(environment="sandbox")
    fake_response = {
        "findCompletedItemsResponse": [{
            "ack": ["Success"],
            "searchResult": [{"item": [], "@count": "0"}],
        }]
    }
    with patch.object(repo, "send", new_callable=AsyncMock) as mock_send, \
         patch.object(repo, "_parse_response", return_value=fake_response), \
         patch.object(repo, "__aenter__", return_value=repo), \
         patch.object(repo, "__aexit__", return_value=False):
        mock_send.return_value = MagicMock()
        await repo.find_completed_items(
            keywords="Sheoldred MH2 MTG",
            app_id="TestApp-123",
            global_id="EBAY-AU",
        )
    call_params = mock_send.call_args[1]["params"]
    assert call_params.get("GLOBAL-ID") == "EBAY-AU"


@pytest.mark.asyncio
async def test_find_completed_items_defaults_global_id_to_us():
    repo = EbayFindingAPIRepository(environment="sandbox")
    fake_response = {
        "findCompletedItemsResponse": [{
            "ack": ["Success"],
            "searchResult": [{"item": [], "@count": "0"}],
        }]
    }
    with patch.object(repo, "send", new_callable=AsyncMock) as mock_send, \
         patch.object(repo, "_parse_response", return_value=fake_response), \
         patch.object(repo, "__aenter__", return_value=repo), \
         patch.object(repo, "__aexit__", return_value=False):
        mock_send.return_value = MagicMock()
        await repo.find_completed_items(
            keywords="Sheoldred MH2 MTG",
            app_id="TestApp-123",
        )
    call_params = mock_send.call_args[1]["params"]
    assert call_params.get("GLOBAL-ID") == "EBAY-US"
