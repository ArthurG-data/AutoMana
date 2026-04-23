"""
Fixtures for the ops service unit tests.
"""
import pytest


def make_check_row(severity: str, check_name: str = "test_check") -> dict:
    """Build a single integrity-check result row."""
    return {
        "check_name": check_name,
        "severity": severity,
        "row_count": 0 if severity == "ok" else 1,
        "details": f"{check_name} details",
    }


@pytest.fixture
def ok_row():
    return make_check_row("ok", "schema_ok")


@pytest.fixture
def warn_row():
    return make_check_row("warn", "orphan_count_warn")


@pytest.fixture
def error_row():
    return make_check_row("error", "fk_orphan_error")
