"""
Tests for src/automana/core/services/app_integration/mtg_stock/data_staging.py
and the ServiceRegistry configuration for those services.

Scope of this file: the NEW `retry_rejects` service (happy path + failure path)
and the execution-flag regressions that matter for the pipeline to run at all
(runs_in_transaction / command_timeout on the three staging CALL/SELECT
services).
"""
from unittest.mock import AsyncMock

import pytest

# Importing the module registers the services via @ServiceRegistry.register.
import automana.core.services.app_integration.mtg_stock.data_staging as staging
from automana.core.service_registry import ServiceRegistry


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
        assert cfg.command_timeout == 3600

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
        assert "boom" in failed_call.kwargs["error_details"]["error"]

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
