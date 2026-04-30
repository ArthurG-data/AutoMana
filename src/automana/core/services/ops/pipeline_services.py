import logging
from contextlib import asynccontextmanager
from automana.core.service_registry import ServiceRegistry
from automana.core.repositories.ops.ops_repository import OpsRepository

logger = logging.getLogger(__name__)


@asynccontextmanager
async def track_step(
    ops_repository: OpsRepository | None,
    ingestion_run_id: int | None,
    step_name: str,
    error_code: str = "step_failed",
):
    """Async context manager that tracks a pipeline step in the ops repository.

    - No-op when ops_repository or ingestion_run_id is None (standalone / test mode).
    - On entry:    marks the step as 'running'.
    - On clean exit: marks the step as 'success'.
    - On exception: marks the step as 'failed' (step row) + 'failed' (run row), then re-raises.
      Both writes are needed: update_run closes the step; fail_run closes the parent run so
      it does not stay stuck as 'running' when the Celery chain halts on this exception.
    """
    if not ops_repository or not ingestion_run_id:
        yield
        return

    await ops_repository.update_run(
        ingestion_run_id, status="running", current_step=step_name
    )
    try:
        yield
    except Exception as e:
        await ops_repository.update_run(
            ingestion_run_id,
            status="failed",
            current_step=step_name,
            error_code=error_code,
            error_details={"message": str(e)},
        )
        await ops_repository.fail_run(
            ingestion_run_id,
            error_code=error_code,
            error_details={"message": str(e), "step": step_name},
        )
        raise
    else:
        await ops_repository.update_run(
            ingestion_run_id, status="success", current_step=step_name
        )

@ServiceRegistry.register(
        "ops.pipeline_services.start_run",
        db_repositories=["ops"]
)
async def start_run(
        ops_repository : OpsRepository,
        run_key: str,
        pipeline_name: str,
        source_name: str,
        celery_task_id: str | None = None
    ) -> int:
    #create a new run entry in the ops repository and return the id
    try:
        ingestion_run_id = await ops_repository.start_run(
            run_key=run_key,
            pipeline_name=pipeline_name,
            source_name=source_name,
            celery_task_id=celery_task_id
        )
    except Exception as e:
        logger.error("Failed to start run", extra={"run_key": run_key, "pipeline_name": pipeline_name, "error": str(e)})
        raise
    logger.info("Pipeline run started", extra={"ingestion_run_id": ingestion_run_id, "run_key": run_key, "pipeline_name": pipeline_name})
    return {"ingestion_run_id": ingestion_run_id}

@ServiceRegistry.register(
        "ops.pipeline_services.finish_run",
        db_repositories=["ops"]
)
async def finish_run(
        ops_repository : OpsRepository,
        ingestion_run_id: int,
        status: str,
        notes: str | None = None,
    ) -> None:
    #update the run entry in the ops repository to mark it as finished
    await ops_repository.finish_run(
        ingestion_run_id=ingestion_run_id,
        status=status,
        notes=notes
    )
