"""Integration tests for HealthAlertService (ops.health.alert_check).

Uses real Postgres (testcontainer) to verify that:
  1. Snapshot rows are correctly persisted for each integrity service.
  2. A second identical run produces no transitions and does not call Discord.
  3. Injecting a synthetic prior-state error row causes the next run to
     detect a recovery transition and call Discord exactly once.

The integrity services themselves are stubbed — their SQL correctness is
covered by their own unit tests. Here we verify persistence, diffing, and
the alerting contract. Discord is always mocked.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from automana.core.repositories.ops.pipeline_health_snapshot_repository import (
    PipelineHealthSnapshotRepository,
)
from automana.core.services.ops import health_alert_service as svc


pytestmark = [pytest.mark.integration]


_CANNED_OK = {
    "check_set": "scryfall_integrity",
    "total_checks": 5,
    "error_count": 0,
    "warn_count": 0,
    "ok_count": 5,
    "errors": [],
    "warnings": [],
    "passed": [],
    "rows": [],
}


async def _run(conn, report=None):
    """Run the service with all side-effects mocked; return (result, poster mock)."""
    repo = PipelineHealthSnapshotRepository(conn)
    poster = AsyncMock(return_value=(204, ""))
    with (
        patch.object(svc, "_discover_integrity_services", return_value=["ops.integrity.scryfall_integrity"]),
        patch.object(svc, "_run_integrity_service", new=AsyncMock(return_value=report or _CANNED_OK)),
        patch.object(svc, "_get_webhook_url", return_value="https://discord.example/webhook"),
        patch.object(svc, "_post_to_discord", new=poster),
    ):
        result = await svc.run_alert_check(pipeline_health_snapshot_repository=repo)
    return result, poster


async def test_rows_persisted_for_each_integrity_service(db_pool):
    async with db_pool.acquire() as conn:
        out, _ = await _run(conn)

    assert out["total_check_sets"] == 1
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT check_set FROM ops.pipeline_health_snapshot WHERE run_id = $1",
            uuid.UUID(out["run_id"]),
        )
    assert len(rows) == 1
    assert rows[0]["check_set"] == "scryfall_integrity"


async def test_second_run_produces_no_transition(db_pool):
    poster = AsyncMock(return_value=(204, ""))
    async with db_pool.acquire() as conn:
        repo = PipelineHealthSnapshotRepository(conn)
        with (
            patch.object(svc, "_discover_integrity_services", return_value=["ops.integrity.scryfall_integrity"]),
            patch.object(svc, "_run_integrity_service", new=AsyncMock(return_value=_CANNED_OK)),
            patch.object(svc, "_get_webhook_url", return_value="https://discord.example/webhook"),
            patch.object(svc, "_post_to_discord", new=poster),
        ):
            await svc.run_alert_check(pipeline_health_snapshot_repository=repo)
            second = await svc.run_alert_check(pipeline_health_snapshot_repository=repo)

    assert second["degraded"] == []
    assert second["recovered"] == []
    assert second["alerted"] is False
    # First run may alert (if there was a prior row from another test with a
    # different status). Second run must never alert when status is unchanged.
    assert poster.await_count <= 1


async def test_injected_error_row_triggers_recovery_on_next_run(db_pool):
    # Establish a baseline run so there is at least one committed 'ok' row.
    async with db_pool.acquire() as conn:
        await _run(conn)

    # Inject a synthetic 'error' snapshot with captured_at strictly after the
    # baseline so it wins the ORDER BY captured_at DESC race for "latest prior".
    injected_run_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO ops.pipeline_health_snapshot
                (run_id, captured_at, check_set, pipeline, status,
                 error_count, warn_count, total_checks, report)
            VALUES
                ($1, now() + interval '50 ms', $2, $3, 'error', 1, 0, 1, '{}'::jsonb)
            """,
            injected_run_id,
            "scryfall_integrity",
            svc.derive_pipeline("scryfall_integrity"),
        )

    # Next run: canned report is still 'ok', injected prior is 'error' → recovered.
    async with db_pool.acquire() as conn:
        out, poster = await _run(conn)

    transitions = out["degraded"] + out["recovered"]
    assert transitions, f"Expected a recovery transition but got none: {out}"
    poster.assert_awaited_once()


async def test_exception_in_integrity_service_writes_synthetic_error_row(db_pool):
    """When an integrity service raises, a synthetic error snapshot must be persisted."""
    async with db_pool.acquire() as conn:
        repo = PipelineHealthSnapshotRepository(conn)
        poster = AsyncMock(return_value=(204, ""))
        with (
            patch.object(svc, "_discover_integrity_services", return_value=["ops.integrity.scryfall_integrity"]),
            patch.object(svc, "_run_integrity_service", new=AsyncMock(side_effect=RuntimeError("DB exploded"))),
            patch.object(svc, "_get_webhook_url", return_value="https://discord.example/webhook"),
            patch.object(svc, "_post_to_discord", new=poster),
        ):
            out = await svc.run_alert_check(pipeline_health_snapshot_repository=repo)

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, report FROM ops.pipeline_health_snapshot WHERE run_id = $1",
            uuid.UUID(out["run_id"]),
        )

    assert row is not None
    assert row["status"] == "error"
    import json
    report = json.loads(row["report"])
    assert "DB exploded" in report.get("exception", "")
