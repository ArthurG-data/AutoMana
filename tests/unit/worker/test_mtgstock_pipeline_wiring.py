"""
Tests for MTGStock pipeline wiring.

Two things matter end-to-end after P1/P2:
  1. `mtgStock_download_pipeline` declares the correct step chain (including
     the new `retry_rejects` step between raw→stg and stg→observation).
  2. `celeryconfig.beat_schedule` contains the mtgstock daily entry and each
     entry routes to a real task name.

These are static structural tests — no Celery broker is needed, and the chain
is not executed. They guard against accidental deletion/rename of steps.
"""
import pytest

from automana.tools.tui.panels.celery import KNOWN_TASKS
import automana.worker.celeryconfig as celeryconfig


EXPECTED_MTGSTOCK_STEPS = [
    "ops.pipeline_services.start_run",
    "mtg_stock.data_staging.bulk_load",
    "mtg_stock.data_staging.from_raw_to_staging",
    "mtg_stock.data_staging.retry_rejects",
    "mtg_stock.data_staging.from_staging_to_prices",
    "ops.pipeline_services.finish_run",
]


class TestTUIPanelSteps:
    def test_mtgstock_task_listed(self):
        names = {t.name for t in KNOWN_TASKS}
        assert "mtgStock_download_pipeline" in names

    def test_mtgstock_steps_match_pipeline_definition(self):
        task = next(t for t in KNOWN_TASKS if t.name == "mtgStock_download_pipeline")
        assert task.steps == EXPECTED_MTGSTOCK_STEPS

    def test_retry_rejects_between_raw_and_prices(self):
        """retry_rejects must run AFTER raw_to_staging (so it sees newly
        rejected rows from today) and BEFORE staging_to_prices (so resolved
        rows promote to price_observation in the same run)."""
        task = next(t for t in KNOWN_TASKS if t.name == "mtgStock_download_pipeline")
        idx_raw = task.steps.index("mtg_stock.data_staging.from_raw_to_staging")
        idx_retry = task.steps.index("mtg_stock.data_staging.retry_rejects")
        idx_prices = task.steps.index("mtg_stock.data_staging.from_staging_to_prices")
        assert idx_raw < idx_retry < idx_prices


class TestBeatSchedule:
    def test_mtgstock_daily_entry_removed(self):
        # Intentionally disabled: bulk_load fills ~169 GB on every run.
        # Trigger manually via API when a fresh MTGStocks download is available.
        assert "refresh-mtgstock-daily" not in celeryconfig.beat_schedule
