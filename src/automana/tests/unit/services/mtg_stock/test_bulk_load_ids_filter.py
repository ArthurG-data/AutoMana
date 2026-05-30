import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
import pandas as pd
from automana.core.services.app_integration.mtg_stock.data_staging import bulk_load


def _make_id_dict(mtgstock_id: int) -> dict:
    return {
        "mtgstock": mtgstock_id,
        "card_name": f"Card {mtgstock_id}",
        "set_abbr": "TST",
        "collector_number": "1",
        "scryfallId": None,
        "tcg_id": None,
        "cardtrader_id": None,
    }


def _make_repos():
    price_repo = MagicMock()
    price_repo.clear_raw_prices = AsyncMock(return_value=0)
    price_repo.copy_prices_mtgstock = AsyncMock()
    price_repo.update_ids_master_dict = AsyncMock()
    ops_repo = MagicMock()
    ops_repo.update_run = AsyncMock()
    ops_repo.insert_batch_step = AsyncMock()
    ops_repo.update_ids_master_dict = AsyncMock()
    return price_repo, ops_repo


@pytest.mark.asyncio
async def test_bulk_load_ids_filter_restricts_folders():
    """bulk_load with ids_filter only processes folders whose names are in the filter."""
    price_repo, ops_repo = _make_repos()
    processed_folders = []

    async def fake_process_info(path):
        folder_id = int(path.split("/")[-2])
        processed_folders.append(folder_id)
        return _make_id_dict(folder_id)

    with patch("os.listdir", return_value=["100", "200", "300", "400", "500", "notdigit"]), \
         patch(
             "automana.core.services.app_integration.mtg_stock.data_staging.process_info_file",
             side_effect=fake_process_info,
         ), \
         patch(
             "automana.core.services.app_integration.mtg_stock.data_staging.process_prices_file",
             new=AsyncMock(return_value=pd.DataFrame(columns=["date", "price_low", "price_avg",
                                                               "price_foil", "price_market",
                                                               "price_market_foil", "print_id",
                                                               "source_code", "card_name",
                                                               "set_abbr", "collector_number",
                                                               "scryfall_id", "tcg_id",
                                                               "cardtrader_id"])),
         ):
        await bulk_load(
            price_repository=price_repo,
            ops_repository=ops_repo,
            root_folder="/fake/path",
            ingestion_run_id=1,
            ids_filter=[200, 400],
        )

    assert sorted(processed_folders) == [200, 400]


@pytest.mark.asyncio
async def test_bulk_load_no_ids_filter_processes_all_digit_folders():
    """bulk_load without ids_filter processes all digit-named folders (existing behaviour)."""
    price_repo, ops_repo = _make_repos()
    processed_folders = []

    async def fake_process_info(path):
        folder_id = int(path.split("/")[-2])
        processed_folders.append(folder_id)
        return _make_id_dict(folder_id)

    with patch("os.listdir", return_value=["100", "200", "notdigit"]), \
         patch(
             "automana.core.services.app_integration.mtg_stock.data_staging.process_info_file",
             side_effect=fake_process_info,
         ), \
         patch(
             "automana.core.services.app_integration.mtg_stock.data_staging.process_prices_file",
             new=AsyncMock(return_value=pd.DataFrame(columns=["date", "price_low", "price_avg",
                                                               "price_foil", "price_market",
                                                               "price_market_foil", "print_id",
                                                               "source_code", "card_name",
                                                               "set_abbr", "collector_number",
                                                               "scryfall_id", "tcg_id",
                                                               "cardtrader_id"])),
         ):
        await bulk_load(
            price_repository=price_repo,
            ops_repository=ops_repo,
            root_folder="/fake/path",
            ingestion_run_id=1,
        )

    assert sorted(processed_folders) == [100, 200]


@pytest.mark.asyncio
async def test_bulk_load_ids_filter_empty_list_processes_nothing():
    """ids_filter=[] means nothing passes the filter — no folders processed."""
    price_repo, ops_repo = _make_repos()
    processed_folders = []

    async def fake_process_info(path):
        processed_folders.append(path)
        return _make_id_dict(0)

    with patch("os.listdir", return_value=["100", "200", "300"]), \
         patch(
             "automana.core.services.app_integration.mtg_stock.data_staging.process_info_file",
             side_effect=fake_process_info,
         ):
        await bulk_load(
            price_repository=price_repo,
            ops_repository=ops_repo,
            root_folder="/fake/path",
            ingestion_run_id=1,
            ids_filter=[],
        )

    assert processed_folders == []
