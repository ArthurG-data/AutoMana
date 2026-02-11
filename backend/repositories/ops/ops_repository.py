import json
from backend.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository
from backend.repositories.ops.scryfall_data import update_bulk_scryfall_data_sql
from backend.schemas.pipelines.mtg_stock import MTGStockBatchStep

class OpsRepository(AbstractRepository):

    @property
    def name(self):
        return "OpsRepository"
    async def insert_batch_step(
            self, 
        batch_step: MTGStockBatchStep
    ):
        query = """
        INSERT INTO ops.ingestion_step_batches (
        ingestion_run_step_id,
        batch_seq,
        range_start,
        range_end,
        status,
        items_ok,
        items_failed,
        bytes_processed,
        duration_ms,
        error_code,
        error_details
    )
    SELECT
        st.id,
        $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
    FROM ops.ingestion_run_steps st
    WHERE st.ingestion_run_id = $1
    AND st.step_name = $2
    LIMIT 1
    ON CONFLICT (ingestion_run_step_id, batch_seq) DO NOTHING;
        """
        await self.execute_query(
            query,
            batch_step.to_tuple()
        )
    #beed to include the ressource upsert as well
    async def start_run(self, 
                        pipeline_name: str,
                          source_name: str,
                          run_key: str,
                          celery_task_id: str = None,
                          notes: str | None = None,
                        ) -> int:
        query = """
        with src as (
        SELECT id 
        FROM ops.sources 
        WHERE name = $2 
        LIMIT 1
        ),
        already_started_successfully as (
            SELECT 1
                FROM ops.ingestion_runs r
                JOIN ops.ingestion_run_steps st
                    ON st.ingestion_run_id = r.id
                AND st.step_name = 'start'
                AND st.status = 'success'
                JOIN src
                    ON r.source_id = src.id
                WHERE r.pipeline_name = $1
                    AND r.run_key = $3
            LIMIT 1
        ),
        upsert_run AS (
            INSERT INTO ops.ingestion_runs (
                pipeline_name,
                source_id,
                run_key,
                celery_task_id,
                status,
                current_step,
                started_at,
                ended_at,
                error_code,
                error_details,
                notes
            )
            SELECT
                $1,
                src.id,
                $3,
                $4,
                'running',
                'start',
                now(),
                NULL,
                NULL,
                NULL,
                $5
            FROM src
            WHERE NOT EXISTS (SELECT 1 FROM already_started_successfully)
            ON CONFLICT (pipeline_name, source_id, run_key) DO UPDATE
            SET
            -- only runs that are NOT "start succeeded" reach here
                status = 'running',
                celery_task_id = COALESCE(EXCLUDED.celery_task_id, ops.ingestion_runs.celery_task_id),
                current_step = 'start',
                error_code = NULL,
                error_details = NULL,
                ended_at = NULL,
                notes = COALESCE(EXCLUDED.notes, ops.ingestion_runs.notes),
                updated_at = now()
            RETURNING id
        ),
        start_step AS (
            INSERT INTO ops.ingestion_run_steps (
                ingestion_run_id,
                step_name,
                status,
                started_at,
                ended_at
            )
            SELECT
                id,
                'start',
                'running',
                now(),
                NULL
            FROM upsert_run
            ON CONFLICT (ingestion_run_id, step_name) DO UPDATE
            SET 
                status = 'running',
                started_at = now(),
                ended_at = NULL,
                error_code = NULL,
                error_details = NULL
            RETURNING ingestion_run_id
            )
            SELECT ingestion_run_id AS id
            FROM start_step;
        """
        result = await self.execute_query(
            query, (pipeline_name, source_name, run_key, celery_task_id, notes))
        return result[0].get("id") if result else None
    
    async def update_run(
        self,
        ingestion_run_id: int,
        *,
        status: str | None = None,
        current_step: str | None = None,
        error_code: str | None = None,
        error_details: dict | None = None,
        notes: str | None = None
    ) -> int | None:
        if error_details is not None and not isinstance(error_details, str):
            error_details = json.dumps(error_details)
        query = """
    WITH desired AS (
        SELECT
            $1::bigint AS ingestion_run_id,
            COALESCE($3::text, (SELECT current_step FROM ops.ingestion_runs WHERE id = $1)) AS step_name,
            COALESCE($2::text, 'running') AS step_status,
            $4::text AS error_code,
            $5::jsonb AS error_details,
            $6::text AS notes
        ),
        step_insert AS (
        INSERT INTO ops.ingestion_run_steps (
            ingestion_run_id, step_name, status, started_at, ended_at, error_code, error_details, notes
        )
        SELECT
            d.ingestion_run_id,
            d.step_name,
            d.step_status,
            now(),
            CASE WHEN d.step_status IN ('success','failed','partial','skipped') THEN now() ELSE NULL END,
            d.error_code,
            d.error_details,
            d.notes
        FROM desired d
        ON CONFLICT (ingestion_run_id, step_name) DO UPDATE
        SET
            status        = EXCLUDED.status,
            error_code    = COALESCE(EXCLUDED.error_code, ops.ingestion_run_steps.error_code),
            error_details = COALESCE(EXCLUDED.error_details, ops.ingestion_run_steps.error_details),
            notes         = COALESCE(EXCLUDED.notes, ops.ingestion_run_steps.notes),
            ended_at      = CASE
                            WHEN EXCLUDED.status IN ('success','failed','partial','skipped')
                            THEN COALESCE(ops.ingestion_run_steps.ended_at, now())
                            ELSE ops.ingestion_run_steps.ended_at
                            END
        WHERE ops.ingestion_run_steps.status <> 'success'
        RETURNING id, ingestion_run_id, step_name, status
)
    SELECT * FROM step_insert;
    """
        result = await self.execute_query(query, 
                                          (ingestion_run_id, status, current_step, error_code, error_details, notes))
        return result[0].get("id") if result else None
    

    async def add_metric(self, ingestion_run_id: int, metric_name: str, metric_value_num: float, metric_value_str: str = None) -> int | None:
        query = """
        INSERT INTO ops.ingestion_run_metrics (
            ingestion_run_id,
            metric_name,
            metric_value_num,
            metric_value_text,
            recorded_at
        )
        VALUES ($1, $2, $3, $4, now())
        ON CONFLICT (ingestion_run_id, metric_name) DO NOTHING
        RETURNING id;
        """
        result = await self.execute_query(query, (ingestion_run_id, metric_name, metric_value_num, metric_value_str))
        return result[0].get("id") if result else None
    
    async def finish_run(
    self,
    ingestion_run_id: int,
    *,
    status: str,  # 'success' or 'partial'
    notes: str | None = None,
    ) -> int | None:
        if status not in ("success", "partial"):
            raise ValueError("finish_run status must be 'success' or 'partial'")

        query = """
        UPDATE ops.ingestion_runs
        SET
        status = $2,
        ended_at = now(),
        current_step = 'finish',
        notes = COALESCE($3, notes),
        updated_at = now()
        WHERE id = $1
        RETURNING id;
        """
        rows = await self.execute_query(query, (ingestion_run_id, status, notes))
        return rows[0]["id"] if rows else None

    async def fail_run(
        self,
        ingestion_run_id: int,
        *,
        error_code: str = "PIPELINE_FAILED",
        error_details: dict | None = None,
        notes: str | None = None,
    ) -> int | None:
        query = """
        UPDATE ops.ingestion_runs
        SET
        status = 'failed',
        ended_at = now(),
        error_code = $2,
        error_details = COALESCE($3::jsonb, error_details),
        notes = COALESCE($4, notes),
        updated_at = now()
        WHERE id = $1
        RETURNING id;
        """
        rows = await self.execute_query(query, (ingestion_run_id, error_code, error_details, notes))
        return rows[0]["id"] if rows else None

    async def get_ingestion_run_status(self, ingestion_run_id: int):
        query = """
        SELECT status
        FROM ops.ingestion_runs
        WHERE id = $1
        """
        result = await self.execute_query(query, (ingestion_run_id,))
        return result[0].get("status") if result and len(result) > 0 else None
    
    async def get_bulk_data_uri(self) -> str | None:
        query = """
        SELECT r.api_uri AS uri, r.source_id AS source_id
        FROM ops.resources r
        JOIN ops.sources s ON s.kind = 'http' and s.name = 'scryfall' AND r.external_type = 'bulk_data'
        ORDER BY s.updated_at DESC
        LIMIT 1
        """
        result = await self.execute_query(query)
        return result[0].get("uri") if result and len(result) > 0 else None
    

    async def update_bulk_data_uri_return_new(self, items: dict, ingestion_run_id: int):
      
        result = await self.execute_query(
    
            update_bulk_scryfall_data_sql,
            (json.dumps(items), ingestion_run_id)#source_id
        )
        record = result[0] if result and len(result) > 0 else None
        ressources_upserted = record.get("resources_upserted") if record else 0
        versions_inserted = record.get("versions_inserted") if record else 0
        changed_items = record.get("changed") if record else []
    
        return {
        "ingestion_run_id": ingestion_run_id,
        "resources_upserted": ressources_upserted,
        "versions_inserted": versions_inserted,
        "changed": changed_items
    }
    async def get():
        raise NotImplementedError("This method is not implemented yet.")
    
    async def add():
        raise NotImplementedError("This method is not implemented yet.")
    async def update():
        raise NotImplementedError("This method is not implemented yet.")
    async def delete():
        raise NotImplementedError("This method is not implemented yet.")
    async def list():
        raise NotImplementedError("This method is not implemented yet.")