"""Unit tests: _iter_sealed_rows helper."""
from __future__ import annotations

from datetime import date

import pytest

pytestmark = [pytest.mark.unit]


def test_iter_sealed_rows_happy_path():
    from automana.core.services.app_integration.mtgjson.data_loader import _iter_sealed_rows

    entry = {
        "paper": {
            "tcgplayer": {
                "currency": "USD",
                "retail": {
                    "foil": {"2026-03-01": 99.99, "2026-02-28": 98.00}
                },
            }
        }
    }
    rows = _iter_sealed_rows("sealed-abc", entry)
    assert len(rows) == 2  # all dates emitted per finish
    dates = {r[5] for r in rows}
    assert date(2026, 3, 1) in dates
    assert date(2026, 2, 28) in dates
    assert all(r[0] == "sealed-abc" for r in rows)
    assert all(r[1] == "tcgplayer" for r in rows)
    assert all(r[2] == "retail" for r in rows)
    assert all(r[3] == "USD" for r in rows)


def test_iter_sealed_rows_no_paper():
    from automana.core.services.app_integration.mtgjson.data_loader import _iter_sealed_rows

    rows = _iter_sealed_rows("sealed-xyz", {"mtgo": {}})
    assert rows == []


def test_iter_sealed_rows_bad_entry():
    from automana.core.services.app_integration.mtgjson.data_loader import _iter_sealed_rows

    rows = _iter_sealed_rows("sealed-xyz", "not a dict")
    assert rows == []
