"""Repository for the ops.pipeline_health_snapshot table.

Conforms to the project's AbstractRepository pattern: takes a single
asyncpg-style connection in __init__, exposes the standard execute_*
helpers from the parent, and stubs the abstract CRUD members because this
repository's domain (snapshot rows for HealthAlertService) doesn't fit the
generic add/get/update/delete/list shape.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from automana.core.repositories.abstract_repositories.AbstractDBRepository import (
    AbstractRepository,
)


@dataclass(frozen=True)
class PipelineHealthSnapshotRow:
    run_id: uuid.UUID
    check_set: str
    pipeline: str
    status: str  # 'ok' | 'warn' | 'error'
    error_count: int
    warn_count: int
    total_checks: int
    report: dict


_INSERT_SQL = """
INSERT INTO ops.pipeline_health_snapshot
    (run_id, check_set, pipeline, status, error_count, warn_count, total_checks, report)
VALUES
    ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
"""

_LATEST_SQL = """
SELECT
    run_id,
    captured_at,
    check_set,
    pipeline,
    status,
    error_count,
    warn_count,
    total_checks,
    report
FROM ops.pipeline_health_snapshot
WHERE check_set = $1
  AND run_id   != $2
ORDER BY captured_at DESC
LIMIT 1
"""


class PipelineHealthSnapshotRepository(AbstractRepository[PipelineHealthSnapshotRow]):
    """Repository for ops.pipeline_health_snapshot.

    Two real methods (insert_snapshots, latest_for_check_set) plus the
    boilerplate ABC stubs that don't apply to this domain.
    """

    @property
    def name(self) -> str:
        return "pipeline_health_snapshot"

    async def insert_snapshots(self, rows: list[PipelineHealthSnapshotRow]) -> None:
        if not rows:
            return
        payload = [
            (
                r.run_id,
                r.check_set,
                r.pipeline,
                r.status,
                r.error_count,
                r.warn_count,
                r.total_checks,
                json.dumps(r.report, default=str),
            )
            for r in rows
        ]
        await self.connection.executemany(_INSERT_SQL, payload)

    async def latest_for_check_set(
        self,
        *,
        check_set: str,
        exclude_run_id: uuid.UUID,
    ) -> Optional[dict[str, Any]]:
        record = await self.connection.fetchrow(_LATEST_SQL, check_set, exclude_run_id)
        if record is None:
            return None
        d = dict(record)
        # asyncpg returns the jsonb column as a str; rehydrate to dict.
        if isinstance(d.get("report"), str):
            d["report"] = json.loads(d["report"])
        return d

    # ABC stubs — this domain doesn't fit add/get/update/delete/list semantics.
    # Mirrors the pattern used in OpsRepository (see ops_repository.py:537-547).
    async def add(self, item):  # pragma: no cover - not used
        raise NotImplementedError

    async def get(self, id: int):  # pragma: no cover - not used
        raise NotImplementedError

    async def update(self, item):  # pragma: no cover - not used
        raise NotImplementedError

    async def delete(self, id: int):  # pragma: no cover - not used
        raise NotImplementedError

    async def list(self, items):  # pragma: no cover - not used
        raise NotImplementedError
