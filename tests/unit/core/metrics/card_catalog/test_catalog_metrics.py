import pytest
from unittest.mock import AsyncMock

from automana.core.metrics.registry import MetricRegistry, Severity
import automana.core.metrics.card_catalog  # noqa: F401
from automana.core.metrics.card_catalog.catalog_metrics import (
    orphan_unique_cards,
    external_id_value_collision,
)

pytestmark = pytest.mark.unit


def _repo(orphans=0, collisions=0):
    repo = AsyncMock()
    repo.fetch_orphan_unique_cards_count.return_value = orphans
    repo.fetch_external_id_value_collisions.return_value = collisions
    return repo


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "n,severity",
    [(0, Severity.OK), (4, Severity.OK), (5, Severity.WARN), (49, Severity.WARN), (50, Severity.ERROR)],
)
async def test_orphan_unique_cards_severity_boundaries(n, severity):
    repo = _repo(orphans=n)
    result = await orphan_unique_cards(card_repository=repo)
    assert result.row_count == n
    cfg = MetricRegistry.get("card_catalog.print_coverage.orphan_unique_cards")
    assert MetricRegistry.evaluate(cfg, result.row_count) == severity


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "n,severity", [(0, Severity.OK), (1, Severity.ERROR), (5, Severity.ERROR)]
)
async def test_external_id_value_collision_severity_boundaries(n, severity):
    repo = _repo(collisions=n)
    result = await external_id_value_collision(card_repository=repo)
    assert result.row_count == n
    cfg = MetricRegistry.get("card_catalog.duplicate_detection.external_id_value_collision")
    assert MetricRegistry.evaluate(cfg, result.row_count) == severity
