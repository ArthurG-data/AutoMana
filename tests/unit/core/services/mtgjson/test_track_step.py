"""Unit tests verifying that MTGJson service functions correctly use track_step.

For three representative steps — download_all_identifiers, sync_uuid_mappings, and
promote_to_price_observation — we assert three paths:

  1. Success path: ops_repository.update_run is awaited with status="running" then
     status="success", and the step name is set on current_step.
  2. Failure path: the inner exception propagates, update_run is called with
     status="failed", and fail_run is also awaited (run never stays stuck as "running").
  3. No-op path: ingestion_run_id=None causes track_step to be a no-op;
     ops_repository.update_run is never awaited.

pytest-asyncio is configured with asyncio_mode=auto (pytest.ini) — no
@pytest.mark.asyncio decorator is needed.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from automana.core.services.app_integration.mtgjson.data_loader import (
    download_all_identifiers,
    promote_to_price_observation,
    sync_uuid_mappings,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _ops_repo() -> AsyncMock:
    """Return a fresh AsyncMock ops repository for each test."""
    return AsyncMock()


# ── download_all_identifiers ──────────────────────────────────────────────────

class TestDownloadAllIdentifiersTrackStep:
    """track_step lifecycle assertions for download_all_identifiers."""

    async def test_success_marks_running_then_success(self):
        ops_repo = _ops_repo()
        mtgjson_repo = AsyncMock()
        # build_path is a sync call on StorageService — use MagicMock so the
        # return value is a plain object, not a coroutine.
        storage = MagicMock()
        storage.build_path.return_value = "/data/mtgjson/raw/AllIdentifiers.json"
        mtgjson_repo.fetch_all_identifiers_stream = AsyncMock(return_value=None)

        result = await download_all_identifiers(
            mtgjson_repository=mtgjson_repo,
            ops_repository=ops_repo,
            storage_service=storage,
            ingestion_run_id=999,
        )

        assert result == {"identifiers_filename": "AllIdentifiers.json"}
        calls = ops_repo.update_run.await_args_list
        assert len(calls) == 2
        assert calls[0].kwargs["status"] == "running"
        assert calls[0].kwargs["current_step"] == "download_all_identifiers"
        assert calls[1].kwargs["status"] == "success"
        assert calls[1].kwargs["current_step"] == "download_all_identifiers"
        ops_repo.fail_run.assert_not_awaited()

    async def test_failure_marks_failed_and_propagates(self):
        ops_repo = _ops_repo()
        mtgjson_repo = AsyncMock()
        storage = MagicMock()
        storage.build_path.return_value = "/data/mtgjson/raw/AllIdentifiers.json"
        mtgjson_repo.fetch_all_identifiers_stream = AsyncMock(
            side_effect=RuntimeError("network timeout")
        )

        with pytest.raises(RuntimeError, match="network timeout"):
            await download_all_identifiers(
                mtgjson_repository=mtgjson_repo,
                ops_repository=ops_repo,
                storage_service=storage,
                ingestion_run_id=999,
            )

        # The failure branch of track_step calls update_run(status="failed") then fail_run.
        failed_calls = [
            c for c in ops_repo.update_run.await_args_list
            if c.kwargs.get("status") == "failed"
        ]
        assert failed_calls, "update_run(status='failed') must be awaited on exception"
        ops_repo.fail_run.assert_awaited_once()

    async def test_noop_when_ingestion_run_id_is_none(self):
        ops_repo = _ops_repo()
        mtgjson_repo = AsyncMock()
        storage = MagicMock()
        storage.build_path.return_value = "/data/mtgjson/raw/AllIdentifiers.json"
        mtgjson_repo.fetch_all_identifiers_stream = AsyncMock(return_value=None)

        result = await download_all_identifiers(
            mtgjson_repository=mtgjson_repo,
            ops_repository=ops_repo,
            storage_service=storage,
            ingestion_run_id=None,
        )

        assert result == {"identifiers_filename": "AllIdentifiers.json"}
        ops_repo.update_run.assert_not_awaited()
        ops_repo.fail_run.assert_not_awaited()


# ── sync_uuid_mappings ────────────────────────────────────────────────────────

class TestSyncUuidMappingsTrackStep:
    """track_step lifecycle assertions for sync_uuid_mappings."""

    async def test_success_marks_running_then_success(self):
        ops_repo = _ops_repo()
        mtgjson_repo = AsyncMock()
        # load_json must return a real dict — the service calls .get("data", raw)
        # then iterates .items() and uses len() arithmetic on the result.
        storage = AsyncMock()
        storage.load_json.return_value = {"data": {}}
        mtgjson_repo.upsert_mtgjson_id_mappings = AsyncMock(return_value=0)

        result = await sync_uuid_mappings(
            mtgjson_repository=mtgjson_repo,
            ops_repository=ops_repo,
            storage_service=storage,
            ingestion_run_id=999,
        )

        assert result == {"mappings_inserted": 0}
        calls = ops_repo.update_run.await_args_list
        assert len(calls) == 2
        assert calls[0].kwargs["status"] == "running"
        assert calls[0].kwargs["current_step"] == "sync_uuid_mappings"
        assert calls[1].kwargs["status"] == "success"
        assert calls[1].kwargs["current_step"] == "sync_uuid_mappings"
        ops_repo.fail_run.assert_not_awaited()

    async def test_success_with_real_identifier_data(self):
        """Smoke-test the UUID-pair extraction logic alongside track_step."""
        ops_repo = _ops_repo()
        mtgjson_repo = AsyncMock()
        storage = AsyncMock()
        storage.load_json.return_value = {
            "data": {
                "uuid-aaa": {
                    "identifiers": {"scryfallId": "scry-111"},
                    "foreignData": [
                        {
                            "uuid": "uuid-bbb",
                            "identifiers": {"scryfallId": "scry-222"},
                        }
                    ],
                }
            }
        }
        mtgjson_repo.upsert_mtgjson_id_mappings = AsyncMock(return_value=2)

        result = await sync_uuid_mappings(
            mtgjson_repository=mtgjson_repo,
            ops_repository=ops_repo,
            storage_service=storage,
            ingestion_run_id=999,
        )

        assert result == {"mappings_inserted": 2}
        # Verify the pairs passed to the repository — both main UUID and foreign UUID.
        call_args = mtgjson_repo.upsert_mtgjson_id_mappings.await_args
        pairs = call_args[0][0]
        assert ("uuid-aaa", "scry-111") in pairs
        assert ("uuid-bbb", "scry-222") in pairs

    async def test_failure_marks_failed_and_propagates(self):
        ops_repo = _ops_repo()
        mtgjson_repo = AsyncMock()
        storage = AsyncMock()
        storage.load_json.side_effect = OSError("file not found")

        with pytest.raises(OSError, match="file not found"):
            await sync_uuid_mappings(
                mtgjson_repository=mtgjson_repo,
                ops_repository=ops_repo,
                storage_service=storage,
                ingestion_run_id=999,
            )

        failed_calls = [
            c for c in ops_repo.update_run.await_args_list
            if c.kwargs.get("status") == "failed"
        ]
        assert failed_calls, "update_run(status='failed') must be awaited on exception"
        ops_repo.fail_run.assert_awaited_once()

    async def test_noop_when_ingestion_run_id_is_none(self):
        ops_repo = _ops_repo()
        mtgjson_repo = AsyncMock()
        storage = AsyncMock()
        storage.load_json.return_value = {"data": {}}
        mtgjson_repo.upsert_mtgjson_id_mappings = AsyncMock(return_value=0)

        result = await sync_uuid_mappings(
            mtgjson_repository=mtgjson_repo,
            ops_repository=ops_repo,
            storage_service=storage,
            ingestion_run_id=None,
        )

        assert result == {"mappings_inserted": 0}
        ops_repo.update_run.assert_not_awaited()
        ops_repo.fail_run.assert_not_awaited()


# ── promote_to_price_observation ──────────────────────────────────────────────

class TestPromoteToPriceObservationTrackStep:
    """track_step lifecycle assertions for promote_to_price_observation."""

    async def test_success_marks_running_then_success(self):
        ops_repo = _ops_repo()
        mtgjson_repo = AsyncMock()
        mtgjson_repo.promote_staging_to_production = AsyncMock(return_value=None)

        result = await promote_to_price_observation(
            mtgjson_repository=mtgjson_repo,
            ops_repository=ops_repo,
            ingestion_run_id=999,
        )

        assert result == {}
        calls = ops_repo.update_run.await_args_list
        assert len(calls) == 2
        assert calls[0].kwargs["status"] == "running"
        assert calls[0].kwargs["current_step"] == "promote_to_price_observation"
        assert calls[1].kwargs["status"] == "success"
        assert calls[1].kwargs["current_step"] == "promote_to_price_observation"
        ops_repo.fail_run.assert_not_awaited()

    async def test_failure_marks_failed_and_propagates(self):
        ops_repo = _ops_repo()
        mtgjson_repo = AsyncMock()
        mtgjson_repo.promote_staging_to_production = AsyncMock(
            side_effect=RuntimeError("promotion proc failed")
        )

        with pytest.raises(RuntimeError, match="promotion proc failed"):
            await promote_to_price_observation(
                mtgjson_repository=mtgjson_repo,
                ops_repository=ops_repo,
                ingestion_run_id=999,
            )

        failed_calls = [
            c for c in ops_repo.update_run.await_args_list
            if c.kwargs.get("status") == "failed"
        ]
        assert failed_calls, "update_run(status='failed') must be awaited on exception"
        ops_repo.fail_run.assert_awaited_once()

    async def test_noop_when_ingestion_run_id_is_none(self):
        ops_repo = _ops_repo()
        mtgjson_repo = AsyncMock()
        mtgjson_repo.promote_staging_to_production = AsyncMock(return_value=None)

        result = await promote_to_price_observation(
            mtgjson_repository=mtgjson_repo,
            ops_repository=ops_repo,
            ingestion_run_id=None,
        )

        assert result == {}
        ops_repo.update_run.assert_not_awaited()
        ops_repo.fail_run.assert_not_awaited()
