"""Unit tests for JSON staging IO helpers."""
from __future__ import annotations

import json
import pytest
from pathlib import Path


def test_write_items_creates_file_with_correct_structure(tmp_path):
    from automana.core.services.app_integration.ebay.ebay_raw_io import write_items_to_json

    p = tmp_path / "EBAY-US.json"
    items = [{"item_id": "A1", "title": "Sheoldred DMU NM", "price": 18.99}]
    write_items_to_json(p, items, marketplace="EBAY-US", source_product_id=None)

    assert p.exists()
    data = json.loads(p.read_text())
    assert data["marketplace"] == "EBAY-US"
    assert data["source_product_id"] is None
    assert data["items"] == items
    assert "fetched_at" in data


def test_write_items_creates_parent_dirs(tmp_path):
    from automana.core.services.app_integration.ebay.ebay_raw_io import write_items_to_json

    p = tmp_path / "deep" / "nested" / "file.json"
    write_items_to_json(p, [], marketplace="EBAY-AU", source_product_id=999)
    assert p.exists()


def test_load_items_returns_list(tmp_path):
    from automana.core.services.app_integration.ebay.ebay_raw_io import (
        load_items_from_json,
        write_items_to_json,
    )

    p = tmp_path / "test.json"
    items = [{"item_id": "B1", "title": "Atraxa ONE", "price": 5.0}]
    write_items_to_json(p, items, marketplace="EBAY-US", source_product_id=42)
    result = load_items_from_json(p)
    assert result == items


def test_load_items_raises_on_corrupt_json(tmp_path):
    from automana.core.services.app_integration.ebay.ebay_raw_io import load_items_from_json

    p = tmp_path / "bad.json"
    p.write_text("not-valid-json{{")
    with pytest.raises(ValueError, match="Corrupt"):
        load_items_from_json(p)


def test_load_items_raises_on_missing_items_key(tmp_path):
    from automana.core.services.app_integration.ebay.ebay_raw_io import load_items_from_json

    p = tmp_path / "missing_key.json"
    p.write_text(json.dumps({"marketplace": "EBAY-US"}))
    with pytest.raises(ValueError, match="Corrupt"):
        load_items_from_json(p)


def test_sweep_path_structure(tmp_path, monkeypatch):
    import automana.core.services.app_integration.ebay.ebay_raw_io as ebay_raw_io

    monkeypatch.setattr(ebay_raw_io, "get_ebay_raw_dir", lambda: tmp_path)
    from automana.core.services.app_integration.ebay.ebay_raw_io import sweep_path

    p = sweep_path("2026-05-24", "EBAY-US")
    assert p == tmp_path / "2026-05-24" / "sweep" / "EBAY-US.json"


def test_watchlist_path_structure(tmp_path, monkeypatch):
    import automana.core.services.app_integration.ebay.ebay_raw_io as ebay_raw_io

    monkeypatch.setattr(ebay_raw_io, "get_ebay_raw_dir", lambda: tmp_path)
    from automana.core.services.app_integration.ebay.ebay_raw_io import watchlist_path

    p = watchlist_path("2026-05-24", 12060647, "EBAY-AU")
    assert p == tmp_path / "2026-05-24" / "watchlist" / "12060647_EBAY-AU.json"
