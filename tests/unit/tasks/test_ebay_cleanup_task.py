"""Unit test: cleanup task deletes files older than 7 days, leaves recent ones."""
from __future__ import annotations

import os
import time
from unittest.mock import patch


def test_cleanup_deletes_old_files(tmp_path):
    from automana.worker.tasks.ebay import _cleanup_old_ebay_raw_files

    old_file = tmp_path / "2026-05-10" / "sweep" / "EBAY-US.json"
    old_file.parent.mkdir(parents=True)
    old_file.write_text("{}")
    old_time = time.time() - (10 * 86400)
    os.utime(old_file, (old_time, old_time))

    recent_file = tmp_path / "2026-05-24" / "sweep" / "EBAY-US.json"
    recent_file.parent.mkdir(parents=True)
    recent_file.write_text("{}")

    with patch("automana.worker.tasks.ebay.get_ebay_raw_dir", return_value=tmp_path):
        deleted = _cleanup_old_ebay_raw_files(max_age_days=7)

    assert not old_file.exists(), "Old file should have been deleted"
    assert recent_file.exists(), "Recent file should be kept"
    assert deleted == 1
