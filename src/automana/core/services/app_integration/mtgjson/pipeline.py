import logging

from automana.core.service_registry import ServiceRegistry
from automana.core.repositories.app_integration.mtgjson.Apimtgjson_repository import ApimtgjsonRepository
from automana.core.repositories.ops.ops_repository import OpsRepository

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    "staging.mtgjson.check_version",
    api_repositories=["mtgjson"],
    db_repositories=["ops"],
)
async def check_version(
    mtgjson_repository: ApimtgjsonRepository,
    ops_repository: OpsRepository,
    ingestion_run_id: int = None,
    **kwargs,
) -> dict:
    """Idempotency gate: compare MTGJson Meta.json version against the stored version.

    Returns version_changed=False to short-circuit Steps 3-6 when the catalog
    has not been updated since the last successful run.
    """
    meta = await mtgjson_repository.fetch_meta()
    fetched_version: str = meta["data"]["version"]
    fetched_date: str = meta["data"]["date"]

    stored_version = await ops_repository.get_mtgjson_resource_version()

    version_changed = stored_version != fetched_version

    if version_changed:
        await ops_repository.upsert_mtgjson_resource_version(fetched_version, fetched_date)
        logger.info(
            "MTGJson version changed — catalog download required",
            extra={
                "ingestion_run_id": ingestion_run_id,
                "old_version": stored_version,
                "new_version": fetched_version,
            },
        )
    else:
        logger.info(
            "MTGJson version unchanged — skipping catalog download",
            extra={"ingestion_run_id": ingestion_run_id, "version": fetched_version},
        )

    return {"version_changed": version_changed, "meta_version": fetched_version}
