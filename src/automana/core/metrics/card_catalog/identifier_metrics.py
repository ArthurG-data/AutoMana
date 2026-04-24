"""card_catalog.identifier_coverage.* metrics.

Coverage = % of card_version rows that have at least one row in
card_external_identifier for the given identifier_name. Per-source thresholds
reflect that scryfall_id and oracle_id should be near-100%, tcgplayer_id and
cardmarket_id naturally lower, and multiverse_id / tcgplayer_etched_id are
informational only (low coverage is expected).
"""
from __future__ import annotations

from automana.core.metrics.registry import MetricRegistry, MetricResult, Threshold
from automana.core.repositories.card_catalog.card_repository import CardReferenceRepository


async def _coverage(card_repository: CardReferenceRepository, name: str) -> MetricResult:
    out = await card_repository.fetch_identifier_coverage_pct(name)
    if out is None:
        return MetricResult(row_count=None, details={"identifier_name": name})
    return MetricResult(
        row_count=out["pct"],
        details={"identifier_name": name, "covered": out["covered"], "total": out["total"]},
    )


async def _count(card_repository: CardReferenceRepository, name: str) -> MetricResult:
    n = await card_repository.fetch_identifier_value_count(name)
    return MetricResult(row_count=n, details={"identifier_name": name})


@MetricRegistry.register(
    path="card_catalog.identifier_coverage.scryfall_id",
    category="health",
    description="% of card_version rows that have a scryfall_id external identifier.",
    severity=Threshold(warn=99, error=95, direction="lower_is_worse"),
    db_repositories=["card"],
)
async def scryfall_id_coverage(card_repository: CardReferenceRepository) -> MetricResult:
    return await _coverage(card_repository, "scryfall_id")


@MetricRegistry.register(
    path="card_catalog.identifier_coverage.oracle_id",
    category="health",
    description="% of card_version rows that have an oracle_id external identifier.",
    severity=Threshold(warn=99, error=95, direction="lower_is_worse"),
    db_repositories=["card"],
)
async def oracle_id_coverage(card_repository: CardReferenceRepository) -> MetricResult:
    return await _coverage(card_repository, "oracle_id")


@MetricRegistry.register(
    path="card_catalog.identifier_coverage.tcgplayer_id",
    category="health",
    description="% of card_version rows that have a tcgplayer_id external identifier.",
    severity=Threshold(warn=80, error=60, direction="lower_is_worse"),
    db_repositories=["card"],
)
async def tcgplayer_id_coverage(card_repository: CardReferenceRepository) -> MetricResult:
    return await _coverage(card_repository, "tcgplayer_id")


@MetricRegistry.register(
    path="card_catalog.identifier_coverage.cardmarket_id",
    category="health",
    description="% of card_version rows that have a cardmarket_id external identifier.",
    severity=Threshold(warn=70, error=50, direction="lower_is_worse"),
    db_repositories=["card"],
)
async def cardmarket_id_coverage(card_repository: CardReferenceRepository) -> MetricResult:
    return await _coverage(card_repository, "cardmarket_id")


@MetricRegistry.register(
    path="card_catalog.identifier_coverage.multiverse_id",
    category="volume",
    description="Count of card_version rows with a (deprecated) multiverse_id identifier.",
    severity=None,
    db_repositories=["card"],
)
async def multiverse_id_count(card_repository: CardReferenceRepository) -> MetricResult:
    return await _count(card_repository, "multiverse_id")


@MetricRegistry.register(
    path="card_catalog.identifier_coverage.tcgplayer_etched_id",
    category="volume",
    description="Count of card_version rows with a tcgplayer_etched_id identifier.",
    severity=None,
    db_repositories=["card"],
)
async def tcgplayer_etched_id_count(card_repository: CardReferenceRepository) -> MetricResult:
    return await _count(card_repository, "tcgplayer_etched_id")
