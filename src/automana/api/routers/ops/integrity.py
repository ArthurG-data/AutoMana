"""
Ops integrity-check endpoints.

Three read-only diagnostic endpoints that execute SQL sanity-check scripts
via the ServiceManager and return structured reports.  All checks are pure
SELECTs — zero side effects — and always return HTTP 200; the payload's
``errors`` and ``warnings`` lists tell the caller whether anything is broken.

Routes:
    GET /ops/integrity/scryfall/run-diff?ingestion_run_id=...
    GET /ops/integrity/scryfall/checks
    GET /ops/integrity/public-schema-leak
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from automana.api.dependancies.service_deps import ServiceManagerDep
from automana.api.schemas.StandardisedQueryResponse import ApiResponse
from automana.api.schemas.ops.integrity import IntegrityCheckReport

logger = logging.getLogger(__name__)

integrity_router = APIRouter(
    prefix="/integrity",
    tags=["ops-integrity"],
    responses={
        500: {"description": "Internal Server Error"},
    },
)


@integrity_router.get(
    "/scryfall/run-diff",
    response_model=ApiResponse[IntegrityCheckReport],
    summary="Scryfall run diff",
    description=(
        "Post-run diagnostic report for the most recent scryfall_daily pipeline run. "
        "Reads ops.ingestion_runs, ops.ingestion_run_steps, ops.ingestion_run_metrics, "
        "and counts sets / cards touched. "
        "Pass ingestion_run_id to inspect a specific run (forward-compatible; the "
        "underlying SQL currently always targets the most recent run)."
    ),
)
async def get_scryfall_run_diff(
    service_manager: ServiceManagerDep,
    ingestion_run_id: Optional[int] = None,
) -> ApiResponse[IntegrityCheckReport]:
    try:
        result = await service_manager.execute_service(
            "ops.integrity.scryfall_run_diff",
            ingestion_run_id=ingestion_run_id,
        )
        report = IntegrityCheckReport(**result)
        return ApiResponse(
            data=report,
            message=f"Run diff complete: {report.total_checks} checks, "
                    f"{len(report.errors)} errors, {len(report.warnings)} warnings.",
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("scryfall_run_diff endpoint failed")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@integrity_router.get(
    "/scryfall/checks",
    response_model=ApiResponse[IntegrityCheckReport],
    summary="Scryfall integrity checks",
    description=(
        "Run 24 orphan / loose-data checks across card_catalog, ops, and pricing. "
        "error severity rows indicate FK-orphan or constraint-violation shaped "
        "findings that should be zero in a healthy database."
    ),
)
async def get_scryfall_integrity(
    service_manager: ServiceManagerDep,
) -> ApiResponse[IntegrityCheckReport]:
    try:
        result = await service_manager.execute_service(
            "ops.integrity.scryfall_integrity",
        )
        report = IntegrityCheckReport(**result)
        return ApiResponse(
            data=report,
            message=f"Integrity checks complete: {report.total_checks} checks, "
                    f"{len(report.errors)} errors, {len(report.warnings)} warnings.",
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("scryfall_integrity endpoint failed")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@integrity_router.get(
    "/public-schema-leak",
    response_model=ApiResponse[IntegrityCheckReport],
    summary="Public schema leak check",
    description=(
        "Confirm that no app objects leaked into the public schema. "
        "Checks tables, views, sequences, functions, and search_path configuration. "
        "Extension-owned objects (pgvector, timescaledb) are excluded."
    ),
)
async def get_public_schema_leak(
    service_manager: ServiceManagerDep,
) -> ApiResponse[IntegrityCheckReport]:
    try:
        result = await service_manager.execute_service(
            "ops.integrity.public_schema_leak",
        )
        report = IntegrityCheckReport(**result)
        return ApiResponse(
            data=report,
            message=f"Public schema check complete: {report.total_checks} checks, "
                    f"{len(report.errors)} errors, {len(report.warnings)} warnings.",
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("public_schema_leak endpoint failed")
        raise HTTPException(status_code=500, detail="Internal Server Error")
