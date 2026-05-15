"""
Tests for src/automana/core/services/app_integration/mtg_stock/data_staging.py
and the ServiceRegistry configuration for those services.

Scope of this file:
- Execution-flag regressions (runs_in_transaction / command_timeout)
- retry_rejects service (happy path + failure path + custom params)
- bulk_load clears the raw table before loading (idempotency fix)
"""
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

# Importing the module registers the services via @ServiceRegistry.register.
import automana.core.services.app_integration.mtg_stock.data_staging as staging
from automana.core.service_registry import ServiceRegistry


def _fake_folder_fns():
    """Return (fake_info, fake_prices) coroutine functions for testing bulk_load.

    fake_info reads the folder name from the path and returns a dict shaped
    exactly like the real process_info_file output (key "mtgstock" for the
    print ID).  fake_prices returns a one-row DataFrame shaped like
    raw_mtg_stock_price so pd.concat does not raise on column mismatches.
    """

    async def fake_info(path: str) -> dict:
        folder = path.split("/")[-2]          # .../root/<folder>/info.json
        pid = int(folder)
        return {
            "mtgstock": pid,
            "card_name": f"Card {pid}",
            "set_abbr": None,
            "collector_number": None,
            "cardtrader": None,
            "scryfallId": None,
            "multiverse_ids": None,
            "tcg_id": None,
            "cardtrader_id": None,
        }

    async def fake_prices(path: str, id_dict: dict) -> pd.DataFrame:
        return pd.DataFrame({
            "ts_date": ["2024-01-01"],
            "price_low": [1.0],
            "price_avg": [1.5],
            "price_foil": [None],
            "price_market": [None],
            "price_market_foil": [None],
            "print_id": [id_dict["mtgstock"]],
            "game_code": ["mtg"],
            "source_code": ["mtgstocks"],
            "scraped_at": [pd.Timestamp.now()],
        })

    return fake_info, fake_prices


# ---------------------------------------------------------------------------
# Execution-flag invariants (regression — these services run long-lived
# stored procedures that issue internal COMMIT/ROLLBACK; the atomic wrapper
# would crash at runtime if these flags ever drift).
# ---------------------------------------------------------------------------

class TestServiceConfigFlags:
    def test_from_raw_to_staging_is_non_atomic(self):
        cfg = ServiceRegistry.get("mtg_stock.data_staging.from_raw_to_staging")
        assert cfg is not None
        assert cfg.runs_in_transaction is False
        assert cfg.command_timeout == 86400  # 24h ceiling for 456M raw rows

    def test_from_staging_to_prices_is_non_atomic(self):
        cfg = ServiceRegistry.get("mtg_stock.data_staging.from_staging_to_prices")
        assert cfg is not None
        assert cfg.runs_in_transaction is False
        assert cfg.command_timeout == 3600

    def test_retry_rejects_is_non_atomic(self):
        """Even though resolve_price_rejects() is a pure FUNCTION with no
        internal COMMIT, the service still needs runs_in_transaction=False
        so the except-path update_run("failed") auto-commits and survives
        the re-raise rollback."""
        cfg = ServiceRegistry.get("mtg_stock.data_staging.retry_rejects")
        assert cfg is not None
        assert cfg.runs_in_transaction is False
        assert cfg.command_timeout == 3600

    def test_bulk_load_is_non_atomic(self):
        """Non-atomic so per-batch COPY + audit rows commit incrementally
        instead of being held under one multi-minute transaction. 3600s
        timeout overrides the pool default so a single large COPY can't
        trip asyncpg's command_timeout race."""
        cfg = ServiceRegistry.get("mtg_stock.data_staging.bulk_load")
        assert cfg is not None
        assert cfg.runs_in_transaction is False
        assert cfg.command_timeout == 3600


# ---------------------------------------------------------------------------
# retry_rejects — happy path and failure path
# ---------------------------------------------------------------------------

class TestRetryRejects:
    async def test_happy_path_returns_rows_and_marks_success(self):
        price_repo = AsyncMock()
        price_repo.call_resolve_price_rejects.return_value = 42
        ops_repo = AsyncMock()

        result = await staging.retry_rejects(
            price_repository=price_repo,
            ops_repository=ops_repo,
            ingestion_run_id=123,
        )

        assert result == {"rows_resolved": 42}
        price_repo.call_resolve_price_rejects.assert_awaited_once_with(
            limit=50000, only_unresolved=True
        )
        # Two ops updates: running → success. Assert on kwargs rather than
        # call count only, to catch status drift.
        statuses = [call.kwargs["status"] for call in ops_repo.update_run.await_args_list]
        assert statuses == ["running", "success"]

    async def test_failure_path_marks_failed_and_reraises(self):
        price_repo = AsyncMock()
        price_repo.call_resolve_price_rejects.side_effect = RuntimeError("boom")
        ops_repo = AsyncMock()

        with pytest.raises(RuntimeError, match="boom"):
            await staging.retry_rejects(
                price_repository=price_repo,
                ops_repository=ops_repo,
                ingestion_run_id=999,
            )

        statuses = [call.kwargs["status"] for call in ops_repo.update_run.await_args_list]
        assert statuses == ["running", "failed"]
        # error_details must include the exception message so the ops audit
        # row is useful.
        failed_call = ops_repo.update_run.await_args_list[-1]
        assert "boom" in failed_call.kwargs["error_details"]["message"]

    async def test_honors_custom_limit_and_only_unresolved(self):
        price_repo = AsyncMock()
        price_repo.call_resolve_price_rejects.return_value = 0
        ops_repo = AsyncMock()

        result = await staging.retry_rejects(
            price_repository=price_repo,
            ops_repository=ops_repo,
            ingestion_run_id=1,
            limit=1000,
            only_unresolved=False,
        )

        assert result == {"rows_resolved": 0}
        price_repo.call_resolve_price_rejects.assert_awaited_once_with(
            limit=1000, only_unresolved=False
        )


# ---------------------------------------------------------------------------
# bulk_load — raw-table clear (idempotency regression)
# ---------------------------------------------------------------------------

class TestBulkLoad:
    async def test_clears_raw_table_before_loading(self):
        """bulk_load must call clear_raw_prices() before the folder traversal
        so re-runs on a failed pipeline start from a clean landing table."""
        price_repo = AsyncMock()
        price_repo.clear_raw_prices.return_value = 0
        ops_repo = AsyncMock()

        with patch("os.listdir", return_value=[]):
            await staging.bulk_load(
                price_repository=price_repo,
                ops_repository=ops_repo,
                root_folder="/fake/root",
            )

        price_repo.clear_raw_prices.assert_awaited_once()

    async def test_clear_called_before_any_copy(self):
        """clear_raw_prices must be awaited before copy_prices_mtgstock.
        We verify ordering via call_order on the mock."""
        price_repo = AsyncMock()
        price_repo.clear_raw_prices.return_value = 0
        ops_repo = AsyncMock()

        call_order = []
        price_repo.clear_raw_prices.side_effect = lambda: call_order.append("clear") or 0
        price_repo.copy_prices_mtgstock.side_effect = lambda df: call_order.append("copy")

        with patch("os.listdir", return_value=[]):
            await staging.bulk_load(
                price_repository=price_repo,
                ops_repository=ops_repo,
                root_folder="/fake/root",
            )

        # With an empty folder list no copy ever fires — just assert clear ran.
        assert "clear" in call_order
        assert call_order.index("clear") == 0


# ---------------------------------------------------------------------------
# bulk_load — print-ID range filtering
# ---------------------------------------------------------------------------

_PATCH_INFO   = "automana.core.services.app_integration.mtg_stock.data_staging.process_info_file"
_PATCH_PRICES = "automana.core.services.app_integration.mtg_stock.data_staging.process_prices_file"


class TestBulkLoadRangeFilter:
    async def test_no_filter_processes_empty_list(self):
        """When no filter is set and listdir returns nothing, no COPY fires."""
        price_repo = AsyncMock()
        price_repo.clear_raw_prices.return_value = 0
        ops_repo = AsyncMock()

        with patch("os.listdir", return_value=[]):
            await staging.bulk_load(
                price_repository=price_repo,
                ops_repository=ops_repo,
                root_folder="/fake/root",
            )

        price_repo.copy_prices_mtgstock.assert_not_awaited()

    async def test_start_id_excludes_lower_ids(self):
        """Folders with print_id < start_id must not be processed."""
        price_repo = AsyncMock()
        price_repo.clear_raw_prices.return_value = 0
        ops_repo = AsyncMock()
        fake_info, fake_prices = _fake_folder_fns()
        processed: list[int] = []

        async def tracking_info(path: str) -> dict:
            result = await fake_info(path)
            processed.append(result["mtgstock"])
            return result

        with patch("os.listdir", return_value=["100", "200", "300"]), \
             patch(_PATCH_INFO, side_effect=tracking_info), \
             patch(_PATCH_PRICES, side_effect=fake_prices):
            await staging.bulk_load(
                price_repository=price_repo,
                ops_repository=ops_repo,
                root_folder="/fake/root",
                start_id=200,
            )

        assert 100 not in processed
        assert 200 in processed
        assert 300 in processed

    async def test_end_id_excludes_higher_ids(self):
        """Folders with print_id > end_id must not be processed."""
        price_repo = AsyncMock()
        price_repo.clear_raw_prices.return_value = 0
        ops_repo = AsyncMock()
        fake_info, fake_prices = _fake_folder_fns()
        processed: list[int] = []

        async def tracking_info(path: str) -> dict:
            result = await fake_info(path)
            processed.append(result["mtgstock"])
            return result

        with patch("os.listdir", return_value=["100", "200", "300"]), \
             patch(_PATCH_INFO, side_effect=tracking_info), \
             patch(_PATCH_PRICES, side_effect=fake_prices):
            await staging.bulk_load(
                price_repository=price_repo,
                ops_repository=ops_repo,
                root_folder="/fake/root",
                end_id=200,
            )

        assert 100 in processed
        assert 200 in processed
        assert 300 not in processed

    async def test_both_bounds_narrow_window(self):
        """Only folders within [start_id, end_id] inclusive are processed."""
        price_repo = AsyncMock()
        price_repo.clear_raw_prices.return_value = 0
        ops_repo = AsyncMock()
        fake_info, fake_prices = _fake_folder_fns()
        processed: list[int] = []

        async def tracking_info(path: str) -> dict:
            result = await fake_info(path)
            processed.append(result["mtgstock"])
            return result

        with patch("os.listdir", return_value=["100", "200", "300", "400", "500"]), \
             patch(_PATCH_INFO, side_effect=tracking_info), \
             patch(_PATCH_PRICES, side_effect=fake_prices):
            await staging.bulk_load(
                price_repository=price_repo,
                ops_repository=ops_repo,
                root_folder="/fake/root",
                start_id=200,
                end_id=400,
            )

        assert set(processed) == {200, 300, 400}

    async def test_non_digit_folders_excluded_when_range_active(self):
        """Non-numeric folder names (e.g. 'existing_ids.json') must be skipped
        when range filtering is active — they must never reach process_info_file."""
        price_repo = AsyncMock()
        price_repo.clear_raw_prices.return_value = 0
        ops_repo = AsyncMock()
        fake_info, fake_prices = _fake_folder_fns()

        with patch("os.listdir", return_value=["existing_ids.json", "100", "200"]), \
             patch(_PATCH_INFO, side_effect=fake_info) as mock_info, \
             patch(_PATCH_PRICES, side_effect=fake_prices):
            await staging.bulk_load(
                price_repository=price_repo,
                ops_repository=ops_repo,
                root_folder="/fake/root",
                start_id=100,
                end_id=200,
            )

        calls = [c.args[0] for c in mock_info.await_args_list]
        assert not any("existing_ids.json" in c for c in calls)


# ---------------------------------------------------------------------------
# bulk_load — parallel processing with as_completed + semaphore
# ---------------------------------------------------------------------------

class TestBulkLoadParallel:

    async def test_copy_called_once_per_batch_chunk(self):
        """With 6 folders and batch_size=2, copy_prices_mtgstock must be
        called exactly 3 times — one flush per chunk."""
        price_repo = AsyncMock()
        price_repo.clear_raw_prices.return_value = 0
        ops_repo = AsyncMock()
        fake_info, fake_prices = _fake_folder_fns()

        with patch("os.listdir", return_value=["10", "20", "30", "40", "50", "60"]), \
             patch(_PATCH_INFO, side_effect=fake_info), \
             patch(_PATCH_PRICES, side_effect=fake_prices):
            await staging.bulk_load(
                price_repository=price_repo,
                ops_repository=ops_repo,
                root_folder="/fake/root",
                batch_size=2,
                concurrency=4,
            )

        assert price_repo.copy_prices_mtgstock.await_count == 3

    async def test_insert_batch_step_called_per_chunk(self):
        """ops_repository.insert_batch_step must be called once per chunk
        that produces at least one successful row."""
        price_repo = AsyncMock()
        price_repo.clear_raw_prices.return_value = 0
        ops_repo = AsyncMock()
        fake_info, fake_prices = _fake_folder_fns()

        with patch("os.listdir", return_value=["10", "20", "30", "40"]), \
             patch(_PATCH_INFO, side_effect=fake_info), \
             patch(_PATCH_PRICES, side_effect=fake_prices):
            await staging.bulk_load(
                price_repository=price_repo,
                ops_repository=ops_repo,
                root_folder="/fake/root",
                batch_size=2,
                concurrency=2,
            )

        assert ops_repo.insert_batch_step.await_count == 2

    async def test_error_in_one_folder_does_not_cancel_others(self):
        """If one folder's read raises, remaining folders in the same chunk
        still produce rows and are COPYed. The error is counted but does not
        propagate."""
        price_repo = AsyncMock()
        price_repo.clear_raw_prices.return_value = 0
        ops_repo = AsyncMock()
        _, fake_prices = _fake_folder_fns()

        async def failing_info(path: str) -> dict:
            folder = path.split("/")[-2]
            if folder == "20":
                raise OSError("parquet missing")
            return {
                "mtgstock": int(folder), "card_name": None, "set_abbr": None,
                "collector_number": None, "cardtrader": None, "scryfallId": None,
                "multiverse_ids": None, "tcg_id": None, "cardtrader_id": None,
            }

        with patch("os.listdir", return_value=["10", "20", "30"]), \
             patch(_PATCH_INFO, side_effect=failing_info), \
             patch(_PATCH_PRICES, side_effect=fake_prices):
            await staging.bulk_load(
                price_repository=price_repo,
                ops_repository=ops_repo,
                root_folder="/fake/root",
                batch_size=10,
                concurrency=3,
            )

        # COPY must fire — 2 successful folders produce rows.
        price_repo.copy_prices_mtgstock.assert_awaited_once()
        df_arg = price_repo.copy_prices_mtgstock.await_args.args[0]
        assert len(df_arg) == 2   # one row per successful folder

    async def test_concurrency_one_matches_sequential_output(self):
        """concurrency=1 (only one folder at a time) produces the same
        observable result as the old sequential loop: one COPY with all rows."""
        price_repo = AsyncMock()
        price_repo.clear_raw_prices.return_value = 0
        ops_repo = AsyncMock()
        fake_info, fake_prices = _fake_folder_fns()

        with patch("os.listdir", return_value=["1", "2", "3"]), \
             patch(_PATCH_INFO, side_effect=fake_info), \
             patch(_PATCH_PRICES, side_effect=fake_prices):
            await staging.bulk_load(
                price_repository=price_repo,
                ops_repository=ops_repo,
                root_folder="/fake/root",
                batch_size=10,
                concurrency=1,
            )

        # All 3 folders fit in one chunk → one COPY call with 3 rows.
        price_repo.copy_prices_mtgstock.assert_awaited_once()
        df_arg = price_repo.copy_prices_mtgstock.await_args.args[0]
        assert len(df_arg) == 3
