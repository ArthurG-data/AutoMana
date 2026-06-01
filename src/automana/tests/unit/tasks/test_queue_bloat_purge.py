import base64
import json
import pytest
from unittest.mock import MagicMock, patch


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_raw(task_name: str, kwargs: dict | None = None) -> bytes:
    """Build a minimal Celery Redis message for a task."""
    body = [[], kwargs or {}, {"callbacks": None, "errbacks": None, "chain": None, "chord": None}]
    return json.dumps({
        "body": base64.b64encode(json.dumps(body).encode()).decode(),
        "headers": {"task": task_name},
        "content-type": "application/json",
        "content-encoding": "utf-8",
        "properties": {"delivery_mode": 2},
    }).encode()


DRAIN = "automana.worker.tasks.ebay_actions.drain_listing_actions_task"
HEALTH = "automana.worker.tasks.pipelines.pipeline_health_alert_task"
RUN_SVC_PRICING = _make_raw("run_service", {"path": "ops.integrity.pricing_report"})
RUN_SVC_CHAIN = _make_raw("run_service", {"path": "mtg_stock.data_staging.bulk_load"})


# ── _build_beat_fingerprints ─────────────────────────────────────────────────

def test_build_beat_fingerprints_includes_named_tasks():
    from automana.worker.main import _build_beat_fingerprints
    fps = _build_beat_fingerprints()
    assert (DRAIN,) in fps
    assert (HEALTH,) in fps


def test_build_beat_fingerprints_includes_run_service_paths():
    from automana.worker.main import _build_beat_fingerprints
    fps = _build_beat_fingerprints()
    assert ("run_service", "ops.integrity.pricing_report") in fps
    assert ("run_service", "ops.integrity.card_catalog_report") in fps


def test_build_beat_fingerprints_excludes_pipeline_chain_paths():
    from automana.worker.main import _build_beat_fingerprints
    fps = _build_beat_fingerprints()
    assert ("run_service", "mtg_stock.data_staging.bulk_load") not in fps
    assert ("run_service", "ops.pipeline_services.start_run") not in fps


# ── _task_fingerprint ─────────────────────────────────────────────────────────

def test_task_fingerprint_named_task():
    from automana.worker.main import _task_fingerprint
    raw = _make_raw(DRAIN)
    assert _task_fingerprint(raw) == (DRAIN,)


def test_task_fingerprint_run_service_with_path():
    from automana.worker.main import _task_fingerprint
    assert _task_fingerprint(RUN_SVC_PRICING) == ("run_service", "ops.integrity.pricing_report")


def test_task_fingerprint_run_service_no_path_returns_none():
    from automana.worker.main import _task_fingerprint
    raw = _make_raw("run_service", {})
    assert _task_fingerprint(raw) is None


def test_task_fingerprint_invalid_json_returns_none():
    from automana.worker.main import _task_fingerprint
    assert _task_fingerprint(b"not json") is None


# ── _purge_stale_beat_tasks ──────────────────────────────────────────────────

def _mock_sender(broker_url="redis://localhost:6379/0"):
    sender = MagicMock()
    sender.app.conf.broker_url = broker_url
    return sender


def test_purge_removes_duplicates_keeps_one():
    from automana.worker.main import _purge_stale_beat_tasks
    drain1 = _make_raw(DRAIN)
    drain2 = _make_raw(DRAIN)
    drain3 = _make_raw(DRAIN)

    mock_redis = MagicMock()
    mock_redis.lrange.return_value = [drain1, drain2, drain3]

    with patch("automana.worker.main.redis_lib.from_url", return_value=mock_redis):
        _purge_stale_beat_tasks(_mock_sender())

    assert mock_redis.lrem.call_count == 2


def test_purge_does_not_touch_pipeline_chain_run_service():
    from automana.worker.main import _purge_stale_beat_tasks
    mock_redis = MagicMock()
    mock_redis.lrange.return_value = [RUN_SVC_CHAIN, RUN_SVC_CHAIN, RUN_SVC_CHAIN]

    with patch("automana.worker.main.redis_lib.from_url", return_value=mock_redis):
        _purge_stale_beat_tasks(_mock_sender())

    mock_redis.lrem.assert_not_called()


def test_purge_no_op_when_single_copy():
    from automana.worker.main import _purge_stale_beat_tasks
    mock_redis = MagicMock()
    mock_redis.lrange.return_value = [_make_raw(DRAIN)]

    with patch("automana.worker.main.redis_lib.from_url", return_value=mock_redis):
        _purge_stale_beat_tasks(_mock_sender())

    mock_redis.lrem.assert_not_called()


def test_purge_no_op_when_queue_empty():
    from automana.worker.main import _purge_stale_beat_tasks
    mock_redis = MagicMock()
    mock_redis.lrange.return_value = []

    with patch("automana.worker.main.redis_lib.from_url", return_value=mock_redis):
        _purge_stale_beat_tasks(_mock_sender())

    mock_redis.lrem.assert_not_called()


def test_purge_logs_warning_when_duplicates_found():
    from automana.worker.main import _purge_stale_beat_tasks
    drain1 = _make_raw(DRAIN)
    drain2 = _make_raw(DRAIN)

    mock_redis = MagicMock()
    mock_redis.lrange.return_value = [drain1, drain2]

    with patch("automana.worker.main.redis_lib.from_url", return_value=mock_redis):
        with patch("automana.worker.main.logger") as mock_logger:
            _purge_stale_beat_tasks(_mock_sender())
            mock_logger.warning.assert_called_once()
            call_extra = mock_logger.warning.call_args[1]["extra"]
            assert "purged" in call_extra


def test_purge_no_warning_when_no_duplicates():
    from automana.worker.main import _purge_stale_beat_tasks
    mock_redis = MagicMock()
    mock_redis.lrange.return_value = [_make_raw(DRAIN)]

    with patch("automana.worker.main.redis_lib.from_url", return_value=mock_redis):
        with patch("automana.worker.main.logger") as mock_logger:
            _purge_stale_beat_tasks(_mock_sender())
            mock_logger.warning.assert_not_called()


# ── _reconcile_orphaned_runs ─────────────────────────────────────────────────

def test_reconcile_calls_run_service():
    from automana.worker.main import _reconcile_orphaned_runs
    sender = MagicMock()
    with patch("automana.worker.main.run_service", return_value={"reconciled": 0, "runs": []}) as mock_rs:
        _reconcile_orphaned_runs(sender)
    mock_rs.assert_called_once_with("ops.pipeline_services.reconcile_orphaned_runs")


def test_reconcile_logs_warning_when_runs_found():
    from automana.worker.main import _reconcile_orphaned_runs
    sender = MagicMock()
    runs = [{"id": 30, "pipeline_name": "mtg_stock_all", "run_key": "mtgStock_All:2026-05-25"}]
    with patch("automana.worker.main.run_service", return_value={"reconciled": 1, "runs": runs}):
        with patch("automana.worker.main.logger") as mock_logger:
            _reconcile_orphaned_runs(sender)
            mock_logger.warning.assert_called_once()
            extra = mock_logger.warning.call_args[1]["extra"]
            assert "reconciled_runs" in extra


def test_reconcile_no_warning_when_no_orphans():
    from automana.worker.main import _reconcile_orphaned_runs
    sender = MagicMock()
    with patch("automana.worker.main.run_service", return_value={"reconciled": 0, "runs": []}):
        with patch("automana.worker.main.logger") as mock_logger:
            _reconcile_orphaned_runs(sender)
            mock_logger.warning.assert_not_called()
