"""Unit tests for PipelineHealthSnapshotRepository.

Mock-based unit tests in the same shape as
tests/unit/core/repositories/app_integration/mtg_stock/test_price_repository.py
— pass an AsyncMock as the connection and assert on the SQL/args sent.
The integration test (Task 8) hits a real DB.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock

import pytest

from automana.core.repositories.ops.pipeline_health_snapshot_repository import (
    PipelineHealthSnapshotRepository,
    PipelineHealthSnapshotRow,
)


def _row(check_set: str, status: str, run_id: uuid.UUID) -> PipelineHealthSnapshotRow:
    return PipelineHealthSnapshotRow(
        run_id=run_id,
        check_set=check_set,
        pipeline=check_set.split("_")[0],
        status=status,
        error_count=1 if status == "error" else 0,
        warn_count=1 if status == "warn" else 0,
        total_checks=5,
        report={"check_set": check_set, "rows": []},
    )


class TestInsertSnapshots:
    async def test_calls_executemany_with_one_tuple_per_row(self):
        connection = AsyncMock()
        repo = PipelineHealthSnapshotRepository(connection=connection)
        run_id = uuid.uuid4()
        rows = [
            _row("scryfall_integrity", "ok", run_id),
            _row("mtgstock_report", "error", run_id),
        ]

        await repo.insert_snapshots(rows)

        connection.executemany.assert_awaited_once()
        sql, payload = connection.executemany.await_args.args
        assert "INSERT INTO ops.pipeline_health_snapshot" in sql
        assert "$8::jsonb" in sql  # report column cast
        assert len(payload) == 2
        # Spot-check the first tuple's positional ordering.
        first = payload[0]
        assert first[0] == run_id
        assert first[1] == "scryfall_integrity"
        # The report must be serialized to a JSON string before insertion.
        assert isinstance(first[7], str)
        assert json.loads(first[7])["check_set"] == "scryfall_integrity"

    async def test_no_rows_skips_db_call(self):
        connection = AsyncMock()
        repo = PipelineHealthSnapshotRepository(connection=connection)
        await repo.insert_snapshots([])
        connection.executemany.assert_not_called()


class TestLatestForCheckSet:
    async def test_runs_select_excluding_current_run_and_returns_dict(self):
        run_id = uuid.uuid4()
        prior_run_id = uuid.uuid4()
        connection = AsyncMock()
        connection.fetchrow.return_value = {
            "run_id": prior_run_id,
            "captured_at": "2026-04-24T10:00:00+00:00",
            "check_set": "scryfall_integrity",
            "pipeline": "scryfall",
            "status": "ok",
            "error_count": 0,
            "warn_count": 0,
            "total_checks": 24,
            # asyncpg returns jsonb columns as str — verify the repo rehydrates.
            "report": json.dumps({"check_set": "scryfall_integrity", "rows": []}),
        }
        repo = PipelineHealthSnapshotRepository(connection=connection)

        result = await repo.latest_for_check_set(
            check_set="scryfall_integrity",
            exclude_run_id=run_id,
        )

        assert result is not None
        assert result["status"] == "ok"
        assert result["run_id"] == prior_run_id
        # report must be a dict, not the raw JSON string we returned above.
        assert isinstance(result["report"], dict)
        assert result["report"]["check_set"] == "scryfall_integrity"

        connection.fetchrow.assert_awaited_once()
        sql, *args = connection.fetchrow.await_args.args
        assert "FROM ops.pipeline_health_snapshot" in sql
        assert "run_id   != $2" in sql or "run_id != $2" in sql
        assert "ORDER BY captured_at DESC" in sql
        assert "LIMIT 1" in sql
        assert args == ["scryfall_integrity", run_id]

    async def test_returns_none_when_no_prior_row(self):
        connection = AsyncMock()
        connection.fetchrow.return_value = None
        repo = PipelineHealthSnapshotRepository(connection=connection)
        result = await repo.latest_for_check_set(
            check_set="x",
            exclude_run_id=uuid.uuid4(),
        )
        assert result is None
