import pytest
from unittest.mock import AsyncMock

from automana.core.metrics.registry import MetricRegistry, Severity
import automana.core.metrics.pricing  # noqa: F401
from automana.core.metrics.pricing.integrity_metrics import (
    product_without_mtg_card_products,
    observation_without_source_product,
    stg_price_observation_residual_count,
    observation_duplicates_on_pk,
)

pytestmark = pytest.mark.unit


def _repo(orphan_pr=0, orphan_obs=0, residual=0, pk_dups=0):
    repo = AsyncMock()
    repo.fetch_orphan_product_ref_mtg_count.return_value = orphan_pr
    repo.fetch_orphan_observation_count.return_value = orphan_obs
    repo.fetch_stg_residual_count.return_value = residual
    repo.fetch_observation_pk_collision_count.return_value = pk_dups
    return repo


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "n,severity", [(0, Severity.OK), (5, Severity.WARN), (20, Severity.ERROR)]
)
async def test_product_without_mtg_card_products_severity(n, severity):
    repo = _repo(orphan_pr=n)
    result = await product_without_mtg_card_products(price_repository=repo)
    assert result.row_count == n
    cfg = MetricRegistry.get("pricing.referential.product_without_mtg_card_products")
    assert MetricRegistry.evaluate(cfg, n) == severity


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "n,severity", [(0, Severity.OK), (1, Severity.WARN), (10, Severity.ERROR)]
)
async def test_observation_without_source_product_severity(n, severity):
    repo = _repo(orphan_obs=n)
    result = await observation_without_source_product(price_repository=repo)
    assert MetricRegistry.evaluate(
        MetricRegistry.get("pricing.referential.observation_without_source_product"), n
    ) == severity


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "n,severity",
    [(0, Severity.OK), (999_999, Severity.OK), (1_000_000, Severity.WARN), (5_000_000, Severity.ERROR)],
)
async def test_stg_residual_severity(n, severity):
    repo = _repo(residual=n)
    result = await stg_price_observation_residual_count(price_repository=repo)
    assert result.row_count == n
    assert MetricRegistry.evaluate(
        MetricRegistry.get("pricing.staging.stg_price_observation_residual_count"), n
    ) == severity


@pytest.mark.asyncio
@pytest.mark.parametrize("n,severity", [(0, Severity.OK), (1, Severity.ERROR)])
async def test_pk_collision_severity(n, severity):
    repo = _repo(pk_dups=n)
    result = await observation_duplicates_on_pk(price_repository=repo)
    assert MetricRegistry.evaluate(
        MetricRegistry.get("pricing.duplicate_detection.observation_duplicates_on_pk"), n
    ) == severity
