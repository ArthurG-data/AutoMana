import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


def _make_identifier_repo(
    existing=None,
    scryfall_map=None,
    tcg_map=None,
    set_col_map=None,
):
    repo = MagicMock()
    repo.get_existing_mapped_print_ids = AsyncMock(return_value=set(existing or []))
    repo.fetch_by_scryfall = AsyncMock(return_value=scryfall_map or {})
    repo.fetch_by_tcgplayer = AsyncMock(return_value=tcg_map or {})
    repo.fetch_by_set_collector = AsyncMock(return_value=set_col_map or {})
    repo.upsert_mtgstock_id_mappings = AsyncMock(return_value=0)
    return repo


def _write_ids(folder: Path, ids: list[int]):
    (folder / "existing_ids.json").write_text(json.dumps(ids))


def _write_info(folder: Path, print_id: int, scryfall_id=None, tcg_id=None,
                set_abbr=None, collector=None):
    d = folder / str(print_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "info.json").write_text(json.dumps({
        "id": print_id,
        "scryfallId": scryfall_id,
        "tcg_id": tcg_id,
        "collector_number": collector,
        "card_set": {"abbreviation": set_abbr} if set_abbr else None,
    }))


@pytest.mark.asyncio
async def test_build_mapping_skips_existing_print_ids(tmp_path):
    """IDs already in card_external_identifier are not re-processed."""
    from automana.core.services.app_integration.mtg_stock.identifier_service import (
        build_mtgstock_id_mapping,
    )
    _write_ids(tmp_path, [1001, 1002, 1003])
    repo = _make_identifier_repo(existing={1001, 1002, 1003})
    ops_repo = MagicMock()
    ops_repo.update_run = AsyncMock()

    result = await build_mtgstock_id_mapping(
        mtg_stock_identifier_repository=repo,
        destination_folder=str(tmp_path),
        ingestion_run_id=1,
        ops_repository=ops_repo,
    )

    assert result["skipped_existing"] == 3
    assert result["mapped"] == 0
    repo.upsert_mtgstock_id_mappings.assert_not_awaited()


@pytest.mark.asyncio
async def test_build_mapping_resolves_by_scryfall_first(tmp_path):
    """scryfall_id match is used before tcgplayer or set+collector fallbacks."""
    from automana.core.services.app_integration.mtg_stock.identifier_service import (
        build_mtgstock_id_mapping,
    )
    _write_ids(tmp_path, [1001])
    _write_info(tmp_path, 1001, scryfall_id="abc-111", tcg_id=999)

    repo = _make_identifier_repo(
        scryfall_map={"abc-111": "uuid-cv-1"},
    )
    ops_repo = MagicMock()
    ops_repo.update_run = AsyncMock()
    repo.upsert_mtgstock_id_mappings = AsyncMock(return_value=1)

    await build_mtgstock_id_mapping(
        mtg_stock_identifier_repository=repo,
        destination_folder=str(tmp_path),
        ingestion_run_id=1,
        ops_repository=ops_repo,
        batch_size=10,
    )

    mappings_passed = repo.upsert_mtgstock_id_mappings.call_args[0][0]
    assert any(m["print_id"] == 1001 and m["card_version_id"] == "uuid-cv-1"
               for m in mappings_passed)


@pytest.mark.asyncio
async def test_build_mapping_falls_back_to_tcgplayer(tmp_path):
    """When scryfall_id yields no match, tcgplayer_id is tried."""
    from automana.core.services.app_integration.mtg_stock.identifier_service import (
        build_mtgstock_id_mapping,
    )
    _write_ids(tmp_path, [1001])
    _write_info(tmp_path, 1001, scryfall_id="abc-111", tcg_id=576888)

    repo = _make_identifier_repo(
        scryfall_map={},
        tcg_map={"576888": "uuid-cv-2"},
    )
    ops_repo = MagicMock()
    ops_repo.update_run = AsyncMock()
    repo.upsert_mtgstock_id_mappings = AsyncMock(return_value=1)

    await build_mtgstock_id_mapping(
        mtg_stock_identifier_repository=repo,
        destination_folder=str(tmp_path),
        ingestion_run_id=1,
        ops_repository=ops_repo,
        batch_size=10,
    )

    mappings_passed = repo.upsert_mtgstock_id_mappings.call_args[0][0]
    assert any(m["print_id"] == 1001 and m["card_version_id"] == "uuid-cv-2"
               for m in mappings_passed)


@pytest.mark.asyncio
async def test_build_mapping_handles_missing_info_json(tmp_path):
    """Print IDs with no info.json on disk are counted as unresolved, not crashed."""
    from automana.core.services.app_integration.mtg_stock.identifier_service import (
        build_mtgstock_id_mapping,
    )
    _write_ids(tmp_path, [1001])
    # intentionally do NOT create info.json for 1001

    repo = _make_identifier_repo()
    ops_repo = MagicMock()
    ops_repo.update_run = AsyncMock()

    result = await build_mtgstock_id_mapping(
        mtg_stock_identifier_repository=repo,
        destination_folder=str(tmp_path),
        ingestion_run_id=1,
        ops_repository=ops_repo,
    )

    assert result["unresolved"] == 1
    assert result["mapped"] == 0


@pytest.mark.asyncio
async def test_build_mapping_returns_counts(tmp_path):
    """Return dict has mapped, skipped_existing, unresolved keys with correct values."""
    from automana.core.services.app_integration.mtg_stock.identifier_service import (
        build_mtgstock_id_mapping,
    )
    _write_ids(tmp_path, [1001, 1002])
    # 1002 already mapped, 1001 has no info.json → unresolved

    repo = _make_identifier_repo(existing={1002})
    ops_repo = MagicMock()
    ops_repo.update_run = AsyncMock()

    result = await build_mtgstock_id_mapping(
        mtg_stock_identifier_repository=repo,
        destination_folder=str(tmp_path),
        ingestion_run_id=1,
        ops_repository=ops_repo,
    )

    assert result["skipped_existing"] == 1
    assert result["unresolved"] == 1
    assert result["mapped"] == 0
