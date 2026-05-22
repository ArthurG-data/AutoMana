"""Unit tests for load_scryfall_prices and PRICE_KEY_MAP.

Verifies:
  - PRICE_KEY_MAP structure contract (fails CI if Scryfall renames a key)
  - Price-cents conversion correctness
  - Skip logic: None prices, missing card id
  - Batch flushing to the pricing repository
"""
import io
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from automana.core.services.app_integration.scryfall.price_loader import (
    PRICE_KEY_MAP,
    load_scryfall_prices,
)


# ── PRICE_KEY_MAP contract ────────────────────────────────────────────────────

class TestPriceKeyMap:
    def test_has_exactly_six_keys(self):
        assert len(PRICE_KEY_MAP) == 6

    def test_expected_scryfall_price_keys_are_present(self):
        assert set(PRICE_KEY_MAP.keys()) == {
            "usd",
            "usd_foil",
            "usd_etched",
            "eur",
            "eur_foil",
            "tix",
        }

    def test_usd_maps_to_tcg_nonfoil(self):
        source, finish = PRICE_KEY_MAP["usd"]
        assert source == "tcg"
        assert finish == "NONFOIL"

    def test_usd_foil_maps_to_tcg_foil(self):
        source, finish = PRICE_KEY_MAP["usd_foil"]
        assert source == "tcg"
        assert finish == "FOIL"

    def test_usd_etched_maps_to_tcg_etched(self):
        source, finish = PRICE_KEY_MAP["usd_etched"]
        assert source == "tcg"
        assert finish == "ETCHED"

    def test_eur_maps_to_cardmarket_nonfoil(self):
        source, finish = PRICE_KEY_MAP["eur"]
        assert source == "cardmarket"
        assert finish == "NONFOIL"

    def test_eur_foil_maps_to_cardmarket_foil(self):
        source, finish = PRICE_KEY_MAP["eur_foil"]
        assert source == "cardmarket"
        assert finish == "FOIL"

    def test_tix_maps_to_cardhoarder_nonfoil(self):
        source, finish = PRICE_KEY_MAP["tix"]
        assert source == "cardhoarder"
        assert finish == "NONFOIL"


# ── load_scryfall_prices behaviour ────────────────────────────────────────────

def _make_stream(cards: list):
    """Return a side_effect for storage_service.open_stream yielding card JSON."""
    data = json.dumps(cards).encode()

    @asynccontextmanager
    async def _inner(*args, **kwargs):
        yield io.BytesIO(data)

    return _inner


def _make_mocks(cards: list):
    pricing_repo = AsyncMock()
    pricing_repo.upsert_scryfall_price_batch.return_value = 0

    card_repo = AsyncMock()
    ops_repo = AsyncMock()

    storage = MagicMock()
    storage.open_stream.side_effect = _make_stream(cards)

    return pricing_repo, card_repo, ops_repo, storage


class TestLoadScryfallPricesSkipLogic:
    async def test_no_file_returns_zero_prices_loaded(self):
        pricing_repo, card_repo, ops_repo, storage = _make_mocks([])
        result = await load_scryfall_prices(
            pricing_repository=pricing_repo,
            card_repository=card_repo,
            ops_repository=ops_repo,
            storage_service=storage,
            file_name=None,
            ingestion_run_id=None,
        )
        assert result == {"prices_loaded": 0}
        pricing_repo.upsert_scryfall_price_batch.assert_not_called()

    async def test_card_without_id_is_skipped(self):
        cards = [{"prices": {"usd": "1.00"}}]  # no "id" key
        pricing_repo, card_repo, ops_repo, storage = _make_mocks(cards)

        await load_scryfall_prices(
            pricing_repository=pricing_repo,
            card_repository=card_repo,
            ops_repository=ops_repo,
            storage_service=storage,
            file_name="bulk.json",
            ingestion_run_id=None,
        )
        pricing_repo.upsert_scryfall_price_batch.assert_not_called()

    async def test_null_price_value_is_skipped(self):
        cards = [{"id": "abc", "prices": {"usd": None, "eur": None, "tix": None}}]
        pricing_repo, card_repo, ops_repo, storage = _make_mocks(cards)

        await load_scryfall_prices(
            pricing_repository=pricing_repo,
            card_repository=card_repo,
            ops_repository=ops_repo,
            storage_service=storage,
            file_name="bulk.json",
            ingestion_run_id=None,
        )
        pricing_repo.upsert_scryfall_price_batch.assert_not_called()

    async def test_card_with_no_prices_key_is_skipped(self):
        cards = [{"id": "abc"}]  # no "prices" key at all
        pricing_repo, card_repo, ops_repo, storage = _make_mocks(cards)

        await load_scryfall_prices(
            pricing_repository=pricing_repo,
            card_repository=card_repo,
            ops_repository=ops_repo,
            storage_service=storage,
            file_name="bulk.json",
            ingestion_run_id=None,
        )
        pricing_repo.upsert_scryfall_price_batch.assert_not_called()


class TestLoadScryfallPricesCentsConversion:
    async def test_price_cents_rounds_correctly(self):
        cards = [{"id": "abc", "prices": {"usd": "1.50"}}]
        pricing_repo, card_repo, ops_repo, storage = _make_mocks(cards)
        pricing_repo.upsert_scryfall_price_batch.return_value = 1

        await load_scryfall_prices(
            pricing_repository=pricing_repo,
            card_repository=card_repo,
            ops_repository=ops_repo,
            storage_service=storage,
            file_name="bulk.json",
            ingestion_run_id=None,
        )

        batch = pricing_repo.upsert_scryfall_price_batch.call_args[0][0]
        usd_row = next(r for r in batch if r["source_code"] == "tcg" and r["finish_code"] == "NONFOIL")
        assert usd_row["price_cents"] == 150

    async def test_all_non_null_prices_produce_records(self):
        cards = [
            {
                "id": "abc",
                "prices": {
                    "usd": "1.00",
                    "usd_foil": "2.00",
                    "usd_etched": "3.00",
                    "eur": "0.90",
                    "eur_foil": "1.80",
                    "tix": "0.10",
                },
            }
        ]
        pricing_repo, card_repo, ops_repo, storage = _make_mocks(cards)
        pricing_repo.upsert_scryfall_price_batch.return_value = 6

        await load_scryfall_prices(
            pricing_repository=pricing_repo,
            card_repository=card_repo,
            ops_repository=ops_repo,
            storage_service=storage,
            file_name="bulk.json",
            ingestion_run_id=None,
        )

        batch = pricing_repo.upsert_scryfall_price_batch.call_args[0][0]
        assert len(batch) == 6

    async def test_small_fractional_price_rounds_correctly(self):
        cards = [{"id": "xyz", "prices": {"tix": "0.03"}}]
        pricing_repo, card_repo, ops_repo, storage = _make_mocks(cards)
        pricing_repo.upsert_scryfall_price_batch.return_value = 1

        await load_scryfall_prices(
            pricing_repository=pricing_repo,
            card_repository=card_repo,
            ops_repository=ops_repo,
            storage_service=storage,
            file_name="bulk.json",
            ingestion_run_id=None,
        )

        batch = pricing_repo.upsert_scryfall_price_batch.call_args[0][0]
        assert batch[0]["price_cents"] == 3


class TestLoadScryfallPricesBatching:
    async def test_purchase_uris_passed_to_card_repository(self):
        cards = [
            {
                "id": "abc",
                "prices": {"usd": "1.00"},
                "purchase_uris": {"tcgplayer": "https://www.tcgplayer.com/123"},
            }
        ]
        pricing_repo, card_repo, ops_repo, storage = _make_mocks(cards)
        pricing_repo.upsert_scryfall_price_batch.return_value = 1

        await load_scryfall_prices(
            pricing_repository=pricing_repo,
            card_repository=card_repo,
            ops_repository=ops_repo,
            storage_service=storage,
            file_name="bulk.json",
            ingestion_run_id=None,
        )

        card_repo.update_purchase_uris_batch.assert_called_once()
        uri_batch = card_repo.update_purchase_uris_batch.call_args[0][0]
        assert uri_batch[0]["scryfall_id"] == "abc"

    async def test_returns_total_prices_loaded(self):
        cards = [
            {"id": "a", "prices": {"usd": "1.00"}},
            {"id": "b", "prices": {"usd": "2.00", "usd_foil": "3.00"}},
        ]
        pricing_repo, card_repo, ops_repo, storage = _make_mocks(cards)
        pricing_repo.upsert_scryfall_price_batch.return_value = 3

        result = await load_scryfall_prices(
            pricing_repository=pricing_repo,
            card_repository=card_repo,
            ops_repository=ops_repo,
            storage_service=storage,
            file_name="bulk.json",
            ingestion_run_id=None,
        )

        assert result["prices_loaded"] == 3
