import pytest
from unittest.mock import MagicMock, patch

PIPELINES = [
    ("automana.worker.tasks.pipelines.daily_scryfall_data_pipeline", "daily_scryfall_data_pipeline"),
    ("automana.worker.tasks.pipelines.mtgStock_download_pipeline", "mtgStock_download_pipeline"),
    ("automana.worker.tasks.pipelines.daily_mtgjson_data_pipeline", "daily_mtgjson_data_pipeline"),
    ("automana.worker.tasks.pipelines.daily_mtgjson_sealed_pipeline", "daily_mtgjson_sealed_pipeline"),
    ("automana.worker.tasks.pipelines.open_tcg_pricing_pipeline", "open_tcg_pricing_pipeline"),
    ("automana.worker.tasks.pipelines.shopify_weekly_pipeline", "shopify_weekly_pipeline"),
    ("automana.worker.tasks.pipelines.mtgstock_build_id_mapping", "mtgstock_build_id_mapping"),
    # Rolling refresh tasks
    ("automana.worker.tasks.pipelines.mtgstock_slice_refresh", "mtgstock_slice_refresh"),
    ("automana.worker.tasks.pipelines.mtgstock_incremental_load", "mtgstock_incremental_load"),
    ("automana.worker.tasks.pipelines.mtgstock_discover_new_ids", "mtgstock_discover_new_ids"),
]

_EXTRA_KWARGS = {
    "mtgstock_slice_refresh": {"hour_slot": 0},
}


def _make_task():
    mock_task = MagicMock()
    mock_task.request.id = "test-celery-task-id"
    return mock_task


@pytest.mark.parametrize("module_path,func_name", PIPELINES)
def test_pipeline_returns_none_when_already_active(module_path, func_name):
    import importlib
    mod = importlib.import_module("automana.worker.tasks.pipelines")
    pipeline_fn = getattr(mod, func_name)

    with patch(
        "automana.worker.tasks.pipelines.run_service",
        return_value={"is_active": True},
    ):
        extra = _EXTRA_KWARGS.get(func_name, {})
        result = pipeline_fn.run.__func__(_make_task(), **extra)

    assert result is None


@pytest.mark.parametrize("module_path,func_name", PIPELINES)
def test_pipeline_guard_calls_is_run_active(module_path, func_name):
    import importlib
    mod = importlib.import_module("automana.worker.tasks.pipelines")
    pipeline_fn = getattr(mod, func_name)

    with patch(
        "automana.worker.tasks.pipelines.run_service",
        return_value={"is_active": True},
    ) as mock_rs:
        extra = _EXTRA_KWARGS.get(func_name, {})
        pipeline_fn.run.__func__(_make_task(), **extra)

    mock_rs.assert_called_once()
    assert mock_rs.call_args[0][0] == "ops.pipeline_services.is_run_active"
    assert "run_key" in mock_rs.call_args[1]
