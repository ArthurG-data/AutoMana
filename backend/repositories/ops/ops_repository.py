import json
from backend.repositories.AbstractRepository import AbstractRepository
from backend.repositories.ops.scryfall_data import update_bulk_scryfall_data_sql, test as test_sql


class OpsRepository(AbstractRepository):

    @property
    def name(self):
        return "OpsRepository"

    async def start_run(self, 
                        pipeline_name: str,
                          source_name: str,
                          run_key: str,
                          celery_task_id: str = None,
                          notes: str | None = None,
                        ) -> int:
        query = """
        INSERT INTO ops.ingestion_runs (
            pipeline_name,
            source_id,
            run_key,
            celery_task_id,
            status,
            current_step,
            progress, notes
        )
        SELECT
            $1,
            s.id,
            $3,
            $4,
            'running',
            'start',
            0.00,
            $5
        FROM ops.sources s
        WHERE s.name = $2
        ON CONFLICT (run_key) DO UPDATE
        SET
            status = 'running',
            celery_task_id = COALESCE(EXCLUDED.celery_task_id, ops.ingestion_runs.celery_task_id),
            current_step = 'start',
            progress = 0.00,
            error_code = NULL,
            error_details = NULL,
            ended_at = NULL,
            notes = COALESCE(EXCLUDED.notes, ops.ingestion_runs.notes),
            updated_at = now()
        RETURNING id;
        """
        result =await self.execute_query(query, (pipeline_name, source_name, run_key, celery_task_id, notes))
        return result[0].get("id") if result and len(result) > 0 else None
    
    async def update_run(
        self,
        run_id: int,
        *,
        status: str | None = None,
        current_step: str | None = None,
        progress: float | None = None,
        error_code: str | None = None,
        error_details: dict | None = None,
        notes: str | None = None
    ) -> int | None:
        if error_details is not None and not isinstance(error_details, str):
            error_details = json.dumps(error_details)
        query = """
        UPDATE ops.ingestion_runs
        SET
            status = COALESCE($2, status),
            current_step = COALESCE($3, current_step),
            progress = COALESCE($4, progress),
            error_code = COALESCE($5, error_code),
            error_details = COALESCE($6::jsonb, error_details),
            notes = COALESCE($7, notes),
            ended_at = CASE
                WHEN COALESCE($2, status) IN ('success','failed','partial') THEN now()
                ELSE ended_at
            END,
            updated_at = now()
        WHERE id = $1
        RETURNING id;
        """
        result = await self.execute_query(query, (run_id, status, current_step, progress, error_code, error_details, notes))
        return result[0].get("id") if result and len(result) > 0 else None
    
    async def finish_run(
    self,
    run_id: int,
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
        progress = 100.00,
        notes = COALESCE($3, notes),
        updated_at = now()
        WHERE id = $1
        RETURNING id;
        """
        rows = await self.execute_query(query, (run_id, status, notes))
        return rows[0]["id"] if rows else None

    async def fail_run(
        self,
        run_id: int,
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
        rows = await self.execute_query(query, (run_id, error_code, error_details, notes))
        return rows[0]["id"] if rows else None

    async def get_ingestion_run_status(self, run_id: int):
        query = """
        SELECT status
        FROM ops.ingestion_runs
        WHERE id = $1
        """
        result = await self.execute_query(query, (run_id,))
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
            #update_bulk_scryfall_data_sql,
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