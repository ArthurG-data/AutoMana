"""Unit tests for Scryfall data-loader service functions.

Covers raw-storage and API-orchestration behaviour without hitting the DB or network.
All functions use track_step which is a no-op when ingestion_run_id is None.
"""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from automana.core.services.app_integration.scryfall.data_loader import (
    delete_old_scryfall_folders,
    download_cards_bulk,
    download_scryfall_bulk_manifests,
    download_scryfall_from_url,
    update_data_uri_in_ops_repository,
)


# ── download_scryfall_bulk_manifests ──────────────────────────────────────────

class TestDownloadScryfallBulkManifests:
    async def test_raises_when_manifest_has_no_data_key(self):
        scryfall_repo = AsyncMock()
        scryfall_repo.download_data_from_url.return_value = {}
        ops_repo = AsyncMock()

        with pytest.raises(ValueError, match="bulk data manifest"):
            await download_scryfall_bulk_manifests(
                ops_repository=ops_repo,
                scryfall_repository=scryfall_repo,
                bulk_uri="https://api.scryfall.com/bulk-data",
                ingestion_run_id=None,
            )

    async def test_raises_when_data_is_empty_list(self):
        scryfall_repo = AsyncMock()
        scryfall_repo.download_data_from_url.return_value = {"data": []}
        ops_repo = AsyncMock()

        with pytest.raises(ValueError):
            await download_scryfall_bulk_manifests(
                ops_repository=ops_repo,
                scryfall_repository=scryfall_repo,
                bulk_uri="https://api.scryfall.com/bulk-data",
                ingestion_run_id=None,
            )

    async def test_returns_items_from_data_key(self, scryfall_bulk_manifest_items):
        scryfall_repo = AsyncMock()
        scryfall_repo.download_data_from_url.return_value = {
            "data": scryfall_bulk_manifest_items
        }
        ops_repo = AsyncMock()

        result = await download_scryfall_bulk_manifests(
            ops_repository=ops_repo,
            scryfall_repository=scryfall_repo,
            bulk_uri="https://api.scryfall.com/bulk-data",
            ingestion_run_id=None,
        )

        assert result == {"items": scryfall_bulk_manifest_items}


# ── update_data_uri_in_ops_repository ─────────────────────────────────────────

class TestUpdateDataUriInOpsRepository:
    async def test_returns_empty_list_when_no_changes(self, scryfall_bulk_manifest_items):
        ops_repo = AsyncMock()
        ops_repo.update_bulk_data_uri_return_new.return_value = {
            "updated": scryfall_bulk_manifest_items,
            "changed": [],
        }

        result = await update_data_uri_in_ops_repository(
            ops_repository=ops_repo,
            items=scryfall_bulk_manifest_items,
            ingestion_run_id=None,
        )

        assert result == {"uris_to_download": []}

    async def test_returns_changed_items(self, scryfall_bulk_manifest_items):
        changed = [
            {
                "resource_id": 1,
                "download_uri": "https://data.scryfall.io/all-cards/all-cards-20250101.json",
                "last_modified": "2025-01-01T00:00:00Z",
                "external_type": "all_cards",
            }
        ]
        ops_repo = AsyncMock()
        ops_repo.update_bulk_data_uri_return_new.return_value = {
            "updated": scryfall_bulk_manifest_items,
            "changed": changed,
        }

        result = await update_data_uri_in_ops_repository(
            ops_repository=ops_repo,
            items=scryfall_bulk_manifest_items,
            ingestion_run_id=None,
        )

        assert result == {"uris_to_download": changed}


# ── download_cards_bulk ───────────────────────────────────────────────────────

class TestDownloadCardsBulk:
    async def test_returns_none_filename_when_no_uris(self):
        result = await download_cards_bulk(
            scryfall_repository=AsyncMock(),
            ops_repository=AsyncMock(),
            ingestion_run_id=None,
            uris_to_download=None,
        )
        assert result == {"file_name": None}

    async def test_returns_none_filename_when_empty_uris(self):
        result = await download_cards_bulk(
            scryfall_repository=AsyncMock(),
            ops_repository=AsyncMock(),
            ingestion_run_id=None,
            uris_to_download=[],
        )
        assert result == {"file_name": None}

    async def test_returns_none_filename_when_no_matching_resource_type(self):
        uris = [
            {
                "download_uri": "https://data.scryfall.io/oracle-cards/...",
                "external_type": "oracle_cards",
            }
        ]
        result = await download_cards_bulk(
            scryfall_repository=AsyncMock(),
            ops_repository=AsyncMock(),
            ingestion_run_id=None,
            uris_to_download=uris,
            resource_type="all_cards",
        )
        assert result == {"file_name": None}

    async def test_calls_stream_download_for_matching_uri(self):
        expected_file = "42_20250101_all-cards-20250101.json"
        uris = [
            {
                "download_uri": "https://data.scryfall.io/all-cards/all-cards-20250101.json",
                "external_type": "all_cards",
            }
        ]
        storage = MagicMock()

        with patch(
            "automana.core.services.app_integration.scryfall.data_loader"
            ".stream_download_scryfall_json_from_uris",
            new_callable=AsyncMock,
            return_value={"files_saved": [expected_file]},
        ) as mock_stream:
            result = await download_cards_bulk(
                scryfall_repository=AsyncMock(),
                ops_repository=AsyncMock(),
                ingestion_run_id=None,
                uris_to_download=uris,
                resource_type="all_cards",
                storage_service=storage,
            )

        mock_stream.assert_called_once()
        assert result == {"file_name": expected_file}

    async def test_non_dict_items_in_uris_are_ignored(self):
        uris = ["not-a-dict", None, 42]
        result = await download_cards_bulk(
            scryfall_repository=AsyncMock(),
            ops_repository=AsyncMock(),
            ingestion_run_id=None,
            uris_to_download=uris,
            resource_type="all_cards",
        )
        assert result == {"file_name": None}


# ── delete_old_scryfall_folders ───────────────────────────────────────────────

class TestDeleteOldScryfallFolders:
    async def test_returns_empty_when_no_files_exist(self):
        storage = AsyncMock()
        storage.list_directory.return_value = []

        result = await delete_old_scryfall_folders(keep=3, storage_service=storage)

        assert result == {"deleted_runs": []}
        storage.delete_files.assert_not_called()

    async def test_no_deletion_when_files_equal_keep(self):
        files = [
            "123_20250103_all-cards.json",
            "122_20250102_all-cards.json",
            "121_20250101_all-cards.json",
        ]
        storage = AsyncMock()
        storage.list_directory.return_value = files

        result = await delete_old_scryfall_folders(keep=3, storage_service=storage)

        # delete_files is called with an empty list (no files to remove)
        storage.delete_files.assert_called_once_with([])
        assert len(result["kept"]) == 3

    async def test_deletes_oldest_files_beyond_keep(self):
        files = [
            "123_20250104_all-cards.json",
            "122_20250103_all-cards.json",
            "121_20250102_all-cards.json",
            "120_20250101_all-cards.json",
            "119_20241231_all-cards.json",
        ]
        storage = AsyncMock()
        storage.list_directory.return_value = files
        storage.delete_files.return_value = [
            "120_20250101_all-cards.json",
            "119_20241231_all-cards.json",
        ]

        result = await delete_old_scryfall_folders(keep=3, storage_service=storage)

        deleted_call = storage.delete_files.call_args[0][0]
        assert len(deleted_call) == 2
        # Most recent 3 must be kept
        assert "123_20250104_all-cards.json" in result["kept"]
        assert "122_20250103_all-cards.json" in result["kept"]
        assert "121_20250102_all-cards.json" in result["kept"]

    async def test_keep_defaults_to_three(self):
        files = [f"run_{str(i).zfill(8)}_all-cards.json" for i in range(5, 0, -1)]
        storage = AsyncMock()
        storage.list_directory.return_value = files
        storage.delete_files.return_value = files[3:]

        result = await delete_old_scryfall_folders(storage_service=storage)

        assert len(result["kept"]) == 3


# ── download_scryfall_from_url ────────────────────────────────────────────────

class TestDownloadScryfallFromUrl:
    async def test_saves_data_to_storage_and_returns_path(self):
        data = {"data": [{"type": "all_cards"}]}
        repo = AsyncMock()
        repo.download_data_from_url.return_value = data

        storage = AsyncMock()

        result = await download_scryfall_from_url(
            repository=repo,
            url="https://api.scryfall.com/sets",
            filename_out="scryfall_sets_20250101.json",
            storage_service=storage,
        )

        storage.save_json.assert_called_once_with(
            "scryfall_sets_20250101.json", data.get("data", {})
        )
        assert result == {"file_path": "scryfall_sets_20250101.json"}
