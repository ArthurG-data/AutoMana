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


async def _coverage_by_unique_card(
    card_repository: CardReferenceRepository, name: str
) -> MetricResult:
    """Variant of _coverage for identifiers that are per-abstract-card (oracle_id).

    Counts coverage against unique_cards_ref instead of card_version. Without
    this, the per-printing denominator divides by the average reprint rate
    (~3x for oracle_id) and produces a false ERROR even when every abstract
    card has its identifier row.
    """
    out = await card_repository.fetch_identifier_coverage_pct_by_unique_card(name)
    if out is None:
        return MetricResult(row_count=None, details={"identifier_name": name})
    return MetricResult(
        row_count=out["pct"],
        details={
            "identifier_name": name,
            "covered": out["covered"],
            "total": out["total"],
            "scope": "unique_cards_ref",
        },
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
    description="% of unique_cards_ref rows whose card_versions have an oracle_id external identifier (per-abstract-card; see HEALTH_METRICS.md).",
    severity=Threshold(warn=99, error=95, direction="lower_is_worse"),
    db_repositories=["card"],
)
async def oracle_id_coverage(card_repository: CardReferenceRepository) -> MetricResult:
    # oracle_id is per-abstract-card: one value is shared across every printing
    # of the same MTG card. Measuring coverage per card_version would under-report
    # by the average reprint rate (~3x). Measuring against unique_cards_ref instead
    # correctly asks "does every abstract card have at least one printing with an
    # oracle_id?" — which is the meaningful question.
    return await _coverage_by_unique_card(card_repository, "oracle_id")


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
