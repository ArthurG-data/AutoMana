"""
Integrity-check services for the ops domain.

Seven read-only diagnostic services that execute SQL sanity-check scripts
against the live database and return structured reports.  All are pure
SELECT workloads — zero side effects — safe to invoke from any role with
SELECT privileges on the relevant schemas.

Registered service keys:
    ops.integrity.scryfall_run_diff    — post-run diff for the most recent (or
                                         specified) scryfall_daily pipeline run.
    ops.integrity.scryfall_integrity   — 24 orphan / loose-data checks across
                                         card_catalog, ops, and pricing.
    ops.integrity.public_schema_leak   — confirms no app objects leaked into
                                         the public schema.
    ops.integrity.pricing_run_diff     — post-run diff for the most recent
                                         mtgStock_download_pipeline run.
    ops.integrity.pricing_integrity    — 10 orphan / loose-data checks across
                                         the pricing domain.
    ops.integrity.mtgjson_run_diff     — post-run diff for the most recent
                                         mtgjson_daily pipeline run.
    ops.integrity.mtgjson_integrity    — 7 orphan / loose-data checks across
                                         the MTGJson pipeline domain.

Each service returns a report dict with the following shape::

    {
        "check_set":     str,               # identifies which check suite ran
        "total_checks":  int,               # total rows returned by the SQL
        "errors":        list[dict],        # rows where severity == "error"
        "warnings":      list[dict],        # rows where severity == "warn"
        "passed":        list[dict],        # rows where severity == "ok"
        "rows":          list[dict],        # full detail — all rows
    }

Each row dict has keys: check_name, severity, row_count, details.
"""

import logging

from automana.core.repositories.ops.ops_repository import OpsRepository
from automana.core.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)


def _build_report(check_set: str, rows: list[dict]) -> dict:
    """Partition rows by severity and assemble the standard report envelope."""
    errors = [r for r in rows if r["severity"] == "error"]
    warnings = [r for r in rows if r["severity"] == "warn"]
    passed = [r for r in rows if r["severity"] == "ok"]

    logger.info(
        "Integrity check complete",
        extra={
            "check_set": check_set,
            "check_count": len(rows),
            "error_count": len(errors),
            "warn_count": len(warnings),
        },
    )

    # Scalar counts placed first so operator-facing viewers (TUI
    # JsonViewer, `curl | jq`, Flower result pane) show pass/fail at
    # a glance without scrolling through the row arrays.
    return {
        "check_set": check_set,
        "total_checks": len(rows),
        "error_count": len(errors),
        "warn_count": len(warnings),
        "ok_count": len(passed),
        "errors": errors,
        "warnings": warnings,
        "passed": passed,
        "rows": rows,
    }


@ServiceRegistry.register(
    "ops.integrity.scryfall_run_diff",
    db_repositories=["ops"],
)
async def scryfall_run_diff(
    ops_repository: OpsRepository,
    ingestion_run_id: int | None = None,
) -> dict:
    """Post-run diff report for the most recent (or a specified) scryfall_daily run.

    The ``ingestion_run_id`` parameter is accepted for forward-compatibility.
    The underlying SQL targets the most recent run by default via an internal
    CTE; it does not yet accept a bind-parameter to override the run.  When the
    SQL is updated to support ``$1``, this service will pass the value through
    without any interface change.

    Returns the standard integrity report envelope (see module docstring).
    """
    rows = await ops_repository.run_scryfall_run_diff(ingestion_run_id=ingestion_run_id)
    return _build_report("scryfall_run_diff", rows)


@ServiceRegistry.register(
    "ops.integrity.scryfall_integrity",
    db_repositories=["ops"],
)
async def scryfall_integrity(
    ops_repository: OpsRepository,
) -> dict:
    """Run the 24-check orphan / loose-data integrity scan for the Scryfall pipeline.

    Covers card_catalog, ops, and pricing schemas.  Non-zero ``error``
    severity rows indicate FK-orphan-shaped or constraint-violation-shaped
    findings that should be zero in a healthy database.

    Returns the standard integrity report envelope (see module docstring).
    """
    rows = await ops_repository.run_scryfall_integrity_checks()
    return _build_report("scryfall_integrity", rows)


@ServiceRegistry.register(
    "ops.integrity.public_schema_leak",
    db_repositories=["ops"],
)
async def public_schema_leak(
    ops_repository: OpsRepository,
) -> dict:
    """Confirm that no app objects leaked into the public schema.

    Extension-owned objects (pgvector, timescaledb) are excluded.  Any
    ``error`` severity row means a card_catalog-domain object was found in
    public — a critical data-routing error.

    Returns the standard integrity report envelope (see module docstring).
    """
    rows = await ops_repository.run_public_schema_leak_check()
    return _build_report("public_schema_leak", rows)


@ServiceRegistry.register(
    "ops.integrity.pricing_run_diff",
    db_repositories=["ops"],
)
async def pricing_run_diff(
    ops_repository: OpsRepository,
    ingestion_run_id: int | None = None,
) -> dict:
    """Post-run diff report for the most recent mtgStock_download_pipeline run.

    Covers run metadata, per-step status, batch-level counters (items_ok /
    items_failed per step), reject table summary (open vs terminal counts with
    top reject reasons), rows promoted to price_observation during the run
    window, and a fast hypertable size heuristic.

    ``ingestion_run_id`` is accepted for forward-compatibility; the underlying
    SQL targets the most recent run via an internal CTE and does not yet
    accept a bind-parameter to override it.

    Returns the standard integrity report envelope (see module docstring).
    """
    rows = await ops_repository.run_pricing_run_diff()
    return _build_report("pricing_run_diff", rows)


@ServiceRegistry.register(
    "ops.integrity.pricing_integrity",
    db_repositories=["ops"],
)
async def pricing_integrity(
    ops_repository: OpsRepository,
) -> dict:
    """Run the 10-check orphan / loose-data integrity scan for the pricing domain.

    Checks:
      - source_product rows with no product_ref (FK orphan)
      - price_observation rows with no source_product (FK orphan)
      - MTG product_ref rows with no mtg_card_products row (dimension gap)
      - Composite-PK violations in price_observation
      - Residual rows in stg_price_observation (should be 0 after inline drain)
      - Open reject row count (informational; large during backfill)
      - Core card_finished codes present (NONFOIL, FOIL, ETCHED)
      - mtgstock_name_finish_suffix seed-data row count (≥ 6 rows expected)
      - Stuck pipeline runs (running > 4 h)
      - Failed steps in most recent run

    Returns the standard integrity report envelope (see module docstring).
    """
    rows = await ops_repository.run_pricing_integrity_checks()
    return _build_report("pricing_integrity", rows)


@ServiceRegistry.register(
    "ops.integrity.mtgjson_run_diff",
    db_repositories=["ops"],
)
async def mtgjson_run_diff(
    ops_repository: OpsRepository,
    ingestion_run_id: int | None = None,
) -> dict:
    """Post-run diff report for the most recent mtgjson_daily run.

    Covers run metadata, per-step status, batch-level counters
    (stream_to_staging and promote_to_price_observation), staging residual
    (fast reltuples estimate), and the resource version consumed.

    ``ingestion_run_id`` is accepted for forward-compatibility; the underlying
    SQL targets the most recent run via an internal CTE.

    Returns the standard integrity report envelope (see module docstring).
    """
    rows = await ops_repository.run_mtgjson_run_diff()
    return _build_report("mtgjson_run_diff", rows)


@ServiceRegistry.register(
    "ops.integrity.mtgjson_integrity",
    db_repositories=["ops"],
)
async def mtgjson_integrity(
    ops_repository: OpsRepository,
) -> dict:
    """Run the 7-check orphan / loose-data integrity scan for the MTGJson pipeline.

    Checks:
      - pricing.data_provider row with code='mtgjson' present
      - Residual rows in pricing.mtgjson_card_prices_staging (should be 0 after run)
      - Legacy pricing.mtgjson_staging should be empty
      - card_external_identifier coverage for identifier_name='mtgjson_id'
      - ops.resources row for canonical_key='mtgjson.all_printings' present
      - Stuck pipeline runs (running > 4 h)
      - Failed steps in most recent run

    No price_observation scans (hypertable shm constraint).

    Returns the standard integrity report envelope (see module docstring).
    """
    rows = await ops_repository.run_mtgjson_integrity_checks()
    return _build_report("mtgjson_integrity", rows)
