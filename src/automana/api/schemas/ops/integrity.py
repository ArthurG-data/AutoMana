"""
Pydantic response schemas for the ops integrity-check endpoints.
"""

from typing import Literal

from pydantic import BaseModel


class IntegrityCheckRow(BaseModel):
    """A single row returned by one of the three integrity-check SQL scripts.

    Columns produced by every check block across all three scripts:
        check_name TEXT, severity TEXT, row_count BIGINT, details JSONB
    """

    check_name: str
    severity: Literal["ok", "warn", "error", "info"]
    row_count: int
    details: dict


class IntegrityCheckReport(BaseModel):
    """Aggregated result of one integrity-check suite.

    Scalar ``*_count`` fields surface pass/fail at a glance so operator
    tooling (TUI, ``curl | jq``) can show status without iterating the
    row arrays. ``errors`` / ``warnings`` / ``passed`` are the
    partitioned row arrays; ``rows`` is the full unfiltered list for
    callers that want every detail.
    """

    check_set: str
    total_checks: int
    error_count: int
    warn_count: int
    ok_count: int
    errors: list[IntegrityCheckRow]
    warnings: list[IntegrityCheckRow]
    passed: list[IntegrityCheckRow]
    rows: list[IntegrityCheckRow]
