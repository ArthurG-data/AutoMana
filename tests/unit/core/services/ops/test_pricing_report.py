import pytest
from unittest.mock import AsyncMock

from automana.core.services.ops.pricing_report import pricing_report

pytestmark = pytest.mark.unit


def _repos():
    price = AsyncMock()
    price.fetch_max_observation_age_days.return_value = 1
    price.fetch_per_source_lag_hours.return_value = {"tcgplayer": 2.0, "mtgstocks": 25.0}
    price.fetch_per_source_observation_coverage_pct.return_value = {"tcgplayer": 95.0}
    price.fetch_orphan_product_ref_mtg_count.return_value = 0
    price.fetch_orphan_observation_count.return_value = 0
    price.fetch_stg_residual_count.return_value = 0
    price.fetch_observation_pk_collision_count.return_value = 0
    ops = AsyncMock()
    return price, ops


@pytest.mark.asyncio
async def test_pricing_report_runs_all_seven_metrics_with_no_filter():
    price, ops = _repos()
    out = await pricing_report(price_repository=price, ops_repository=ops)
    assert out["check_set"] == "pricing_report"
    assert out["total_checks"] == 7
    paths = {r["check_name"] for r in out["rows"]}
    expected = {
        "pricing.freshness.price_observation_max_age_days",
        "pricing.freshness.max_per_source_lag_hours",
        "pricing.coverage.min_per_source_observation_coverage_pct",
        "pricing.referential.product_without_mtg_card_products",
        "pricing.referential.observation_without_source_product",
        "pricing.staging.stg_price_observation_residual_count",
        "pricing.duplicate_detection.observation_duplicates_on_pk",
    }
    assert paths == expected


@pytest.mark.asyncio
async def test_pricing_report_category_filter_health_only_excludes_volume_and_timing():
    price, ops = _repos()
    out = await pricing_report(price_repository=price, ops_repository=ops, category="health")
    paths = {r["check_name"] for r in out["rows"]}
    assert "pricing.freshness.price_observation_max_age_days" not in paths
    assert "pricing.staging.stg_price_observation_residual_count" not in paths
    assert "pricing.referential.product_without_mtg_card_products" in paths


@pytest.mark.asyncio
async def test_pricing_report_one_failing_metric_does_not_kill_report():
    price, ops = _repos()
    price.fetch_max_observation_age_days.side_effect = RuntimeError("db down")
    out = await pricing_report(price_repository=price, ops_repository=ops)
    assert out["error_count"] == 1
    assert out["total_checks"] == 7
