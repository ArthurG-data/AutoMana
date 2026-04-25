"""card_catalog.* non-identifier metrics: catalog hygiene + collision detection."""
from __future__ import annotations

from automana.core.metrics.registry import MetricRegistry, MetricResult, Threshold
from automana.core.repositories.card_catalog.card_repository import CardReferenceRepository


@MetricRegistry.register(
    path="card_catalog.print_coverage.orphan_unique_cards",
    category="health",
    description="Count of unique_cards_ref rows with zero card_version children.",
    severity=Threshold(warn=5, error=50, direction="higher_is_worse"),
    db_repositories=["card"],
)
async def orphan_unique_cards(card_repository: CardReferenceRepository) -> MetricResult:
    n = await card_repository.fetch_orphan_unique_cards_count()
    return MetricResult(row_count=n)


@MetricRegistry.register(
    path="card_catalog.duplicate_detection.external_id_value_collision",
    category="health",
    description="Count of (card_identifier_ref_id, value) tuples appearing more than once (UNIQUE-constraint guard).",
    severity=Threshold(warn=1, error=1, direction="higher_is_worse"),
    db_repositories=["card"],
)
async def external_id_value_collision(card_repository: CardReferenceRepository) -> MetricResult:
    n = await card_repository.fetch_external_id_value_collisions()
    return MetricResult(row_count=n)
