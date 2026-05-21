"""Static structural tests for the daily_mtgjson_data_pipeline chain.

No Celery broker needed — tests inspect the KNOWN_TASKS registry and
beat_schedule config, guarding against accidental step deletion or reordering.
"""
import automana.worker.celeryconfig as celeryconfig
from automana.tools.tui.panels.celery import KNOWN_TASKS


EXPECTED_MTGJSON_STEPS = [
    "ops.pipeline_services.start_run",
    "mtgjson.data.download.all_identifiers",
    "staging.mtgjson.sync_uuid_mappings",
    "mtgjson.data.download.today",
    "staging.mtgjson.stream_to_staging",
    "staging.mtgjson.promote_to_price_observation",
    "staging.mtgjson.cleanup_raw_files",
    "ops.pipeline_services.finish_run",
]


class TestTUIPanelSteps:
    def test_mtgjson_task_listed(self):
        names = {t.name for t in KNOWN_TASKS}
        assert "daily_mtgjson_data_pipeline" in names

    def test_mtgjson_steps_match_expected(self):
        task = next(t for t in KNOWN_TASKS if t.name == "daily_mtgjson_data_pipeline")
        assert task.steps == EXPECTED_MTGJSON_STEPS

    def test_identifiers_download_before_price_download(self):
        """download.all_identifiers must run before download.today so UUID
        mappings are always current when prices are staged and promoted."""
        task = next(t for t in KNOWN_TASKS if t.name == "daily_mtgjson_data_pipeline")
        idx_ident = task.steps.index("mtgjson.data.download.all_identifiers")
        idx_sync = task.steps.index("staging.mtgjson.sync_uuid_mappings")
        idx_prices = task.steps.index("mtgjson.data.download.today")
        assert idx_ident < idx_sync < idx_prices


class TestBeatSchedule:
    def test_mtgjson_daily_entry_exists(self):
        assert "refresh-mtgjson-daily" in celeryconfig.beat_schedule

    def test_mtgjson_entry_routes_to_pipeline_task(self):
        entry = celeryconfig.beat_schedule["refresh-mtgjson-daily"]
        assert entry["task"] == (
            "automana.worker.tasks.pipelines.daily_mtgjson_data_pipeline"
        )
