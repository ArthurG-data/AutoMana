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
    assert len(rows) == 1  # one date per finish (break after first)
    assert rows[0][0] == "sealed-abc"
    assert rows[0][1] == "tcgplayer"
    assert rows[0][2] == "retail"
    assert rows[0][3] == "USD"
    assert rows[0][4] == 99.99
    assert rows[0][5] == date(2026, 3, 1)


def test_iter_sealed_rows_no_paper():
    from automana.core.services.app_integration.mtgjson.data_loader import _iter_sealed_rows

    rows = _iter_sealed_rows("sealed-xyz", {"mtgo": {}})
    assert rows == []


def test_iter_sealed_rows_bad_entry():
    from automana.core.services.app_integration.mtgjson.data_loader import _iter_sealed_rows

    rows = _iter_sealed_rows("sealed-xyz", "not a dict")
    assert rows == []
