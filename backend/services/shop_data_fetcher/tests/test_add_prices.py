import pytest
from unittest.mock import MagicMock, patch
from backend.services.shop_data_fetcher.fetcher_services.add_prices import validate_batch, bulk_insert, stream_json_file
import tempfile
import json
from datetime import datetime

def test_validate_batch_valid():
    batch = [
        {
            "product_id": "123",
            "shop_id": "1",
            "price": 10.5,
            "date": "2025-07-05T12:00:00"
        }
    ]
    # Should not raise
    result = validate_batch(batch)
    assert len(result[0]) == 1  # p_times
    assert len(result[1]) == 1  # p_product_shop_ids
    assert len(result[2]) == 1  # p_prices
    assert len(result[3]) == 1  # p_sources

def test_validate_batch_invalid():
    batch = [{}]  # Missing required fields
    with pytest.raises(ValueError):
        validate_batch(batch)

def test_bulk_insert_calls_proc():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    batch = ([datetime.now()], ["abc"], [10.5], ["source"])
    bulk_insert(batch, mock_conn)
    mock_cursor.callproc.assert_called_once()
    mock_conn.commit.assert_called_once()

def test_stream_json_file(monkeypatch):
    # Prepare a small JSON file
    data = [
        {"id": "1", "variants": [{"price": 5.0}], "updated_at": "2025-07-05T12:00:00"}
    ]
    with tempfile.NamedTemporaryFile(mode='w+', delete=False, encoding='utf-8') as tmp:
        json.dump(data, tmp)
        tmp.flush()
        # Patch validate_batch and bulk_insert to just check they are called
        with patch('backend.services.shop_data_fetcher.fetcher_services.add_prices.validate_batch') as mock_validate, \
             patch('backend.services.shop_data_fetcher.fetcher_services.add_prices.bulk_insert') as mock_bulk:
            stream_json_file(tmp.name, 1, batch_size=1)
            mock_validate.assert_called()
            mock_bulk.assert_called()