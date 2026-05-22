"""Static structural tests for the daily_scryfall_data_pipeline chain.

No Celery broker needed — tests inspect KNOWN_TASKS and beat_schedule config,
guarding against accidental step deletion or reordering.
"""
import automana.worker.celeryconfig as celeryconfig
from automana.tools.tui.panels.celery import KNOWN_TASKS


EXPECTED_SCRYFALL_STEPS = [
    "staging.scryfall.start_pipeline",
    "staging.scryfall.get_bulk_data_uri",
    "staging.scryfall.download_bulk_manifests",
    "staging.scryfall.update_data_uri_in_ops_repository",
    "staging.scryfall.download_sets",
    "card_catalog.set.process_large_sets_json",
    "staging.scryfall.download_cards_bulk",
    "card_catalog.card.process_large_json",
    "staging.scryfall.load_prices_from_bulk",
    "card_catalog.card_search.refresh",
    "card_catalog.card_search.invalidate",
    "staging.scryfall.download_and_load_migrations",
    "ops.pipeline_services.finish_run",
    "staging.scryfall.delete_old_scryfall_folders",
    "ops.integrity.scryfall_run_diff",
    "ops.integrity.scryfall_integrity",
    "ops.integrity.public_schema_leak",
]


class TestTUIPanelSteps:
    def test_scryfall_pipeline_listed(self):
        names = {t.name for t in KNOWN_TASKS}
        assert "daily_scryfall_data_pipeline" in names

    def test_scryfall_steps_match_expected(self):
        task = next(t for t in KNOWN_TASKS if t.name == "daily_scryfall_data_pipeline")
        assert task.steps == EXPECTED_SCRYFALL_STEPS

    def test_sets_processed_before_cards_downloaded(self):
        """Sets must be loaded before cards so set FK constraints are satisfied."""
        task = next(t for t in KNOWN_TASKS if t.name == "daily_scryfall_data_pipeline")
        idx_sets_dl = task.steps.index("staging.scryfall.download_sets")
        idx_sets_proc = task.steps.index("card_catalog.set.process_large_sets_json")
        idx_cards = task.steps.index("staging.scryfall.download_cards_bulk")
        assert idx_sets_dl < idx_sets_proc < idx_cards

    def test_finish_run_before_cleanup(self):
        """finish_run must complete before folder cleanup so the run is not left open."""
        task = next(t for t in KNOWN_TASKS if t.name == "daily_scryfall_data_pipeline")
        idx_finish = task.steps.index("ops.pipeline_services.finish_run")
        idx_cleanup = task.steps.index("staging.scryfall.delete_old_scryfall_folders")
        assert idx_finish < idx_cleanup

    def test_integrity_checks_after_finish_run(self):
        """Integrity checks are diagnostic-only and must not block the finish step."""
        task = next(t for t in KNOWN_TASKS if t.name == "daily_scryfall_data_pipeline")
        idx_finish = task.steps.index("ops.pipeline_services.finish_run")
        idx_diff = task.steps.index("ops.integrity.scryfall_run_diff")
        idx_integrity = task.steps.index("ops.integrity.scryfall_integrity")
        assert idx_finish < idx_diff
        assert idx_finish < idx_integrity

    def test_integrity_checks_task_listed(self):
        names = {t.name for t in KNOWN_TASKS}
        assert "run_scryfall_integrity_checks" in names


class TestBeatSchedule:
    def test_scryfall_nightly_entry_exists(self):
        assert "refresh-scryfall-manifest-nightly" in celeryconfig.beat_schedule

    def test_scryfall_entry_routes_to_pipeline_task(self):
        entry = celeryconfig.beat_schedule["refresh-scryfall-manifest-nightly"]
        assert entry["task"] == (
            "automana.worker.tasks.pipelines.daily_scryfall_data_pipeline"
        )

    def test_scryfall_runs_before_mtgjson_and_mtgstock(self):
        """Scryfall must run first so migration table is fresh for downstream pipelines.

        crontab.hour is a frozenset, so use min() for numeric comparison.
        """
        hours = {
            name: min(entry["schedule"].hour)
            for name, entry in celeryconfig.beat_schedule.items()
            if "schedule" in entry and hasattr(entry["schedule"], "hour")
        }
        scryfall = hours.get("refresh-scryfall-manifest-nightly")
        mtgjson = hours.get("refresh-mtgjson-daily")
        mtgstock = hours.get("refresh-mtgstock-daily")
        assert scryfall < mtgjson
        assert scryfall < mtgstock
