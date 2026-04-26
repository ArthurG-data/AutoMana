import json
import logging
from datetime import date as date_type
from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository
from automana.core.repositories.ops.scryfall_data import update_bulk_scryfall_data_sql
from automana.core.repositories.ops.integrity_check_sql import (
    scryfall_run_diff_sql,
    scryfall_integrity_checks_sql,
    public_schema_leak_check_sql,
)
from automana.core.models.pipelines.mtg_stock import MTGStockBatchStep

logger = logging.getLogger(__name__)


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
            -- Only block re-runs for fully successful pipelines.
            -- A failed or partial run must be retriable on the same day,
            -- so we guard on the run row's final status, not the 'start'
            -- step alone (which always succeeds even when the run later fails).
            SELECT 1
                FROM ops.ingestion_runs r
                JOIN src ON r.source_id = src.id
                WHERE r.pipeline_name = $1
                    AND r.run_key = $3
                    AND r.status = 'success'
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
            -- 'start' is an instantaneous marker step: the only work it
            -- wraps is "the run row was created", which we just did in the
            -- upsert_run CTE. Close it immediately so the run does not end
            -- with a dangling 'running' step, which would otherwise trip
            -- the last-run-failed-steps integrity check on every success.
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
                'success',
                now(),
                now()
            FROM upsert_run
            ON CONFLICT (ingestion_run_id, step_name) DO UPDATE
            SET
                status = 'success',
                started_at = now(),
                ended_at = now(),
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
),
        -- Advance ingestion_runs.current_step so operator-facing pollers
        -- (rebuild_dev_db.sh, TUI, dashboard) see which step is executing.
        -- Never touch the parent run's terminal status from here — only
        -- finish_run / fail_run may set 'success'/'failed'/'partial' on
        -- the run row. This CTE only advances current_step and keeps the
        -- run in 'running' while steps progress.
        run_update AS (
            UPDATE ops.ingestion_runs
            SET
                current_step = COALESCE((SELECT step_name FROM desired), current_step),
                updated_at   = now()
            WHERE id = $1::bigint
              AND status = 'running'
            RETURNING id
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
        if error_details is not None and not isinstance(error_details, str):
            error_details = json.dumps(error_details)
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
    

    async def update_bulk_data_uri_return_new(self, items: dict, ingestion_run_id: int = None) -> dict:
       
        result = await self.execute_query(
    
            update_bulk_scryfall_data_sql,
            (json.dumps(items), ingestion_run_id)#source_id
        )
        logger.debug("update_bulk_data_uri_return_new result", extra={"result": result})
        record = result[0] if result and len(result) > 0 else None
        ressources_upserted = record.get("resources_upserted") if record else 0
        versions_inserted = record.get("versions_inserted") if record else 0
        changed_raw = record.get("changed") if record else "[]"
        # asyncpg returns jsonb columns as raw JSON strings — parse to Python list
        changed_items = json.loads(changed_raw) if isinstance(changed_raw, str) else (changed_raw or [])

        return {
        "ingestion_run_id": ingestion_run_id,
        "resources_upserted": ressources_upserted,
        "versions_inserted": versions_inserted,
        "changed": changed_items
    }
    async def update_ids_master_dict(self, ingestion_run_id: int, ids_master_dict: dict):
        # RETURNING cannot aggregate (Postgres rejects aggregates in RETURNING).
        # Wrap in a CTE so the COUNT runs over the upserted rows in the
        # outer SELECT instead.
        query = """
        WITH upsert AS (
            INSERT INTO ops.ingestion_ids_mapping (
                ingestion_run_id,
                mtgstock_id,
                scryfall_id,
                multiverse_id,
                tcg_id
            )
            SELECT
                $1,
                (key::BIGINT),
                (value->>'scryfall_id')::UUID,
                (value->>'multiverse_id')::BIGINT,
                (value->>'tcg_id')::BIGINT
            FROM jsonb_each($2::jsonb)
            ON CONFLICT (ingestion_run_id, mtgstock_id) DO UPDATE
            SET
                scryfall_id = EXCLUDED.scryfall_id,
                multiverse_id = EXCLUDED.multiverse_id,
                tcg_id = EXCLUDED.tcg_id,
                created_at = NOW()
            RETURNING 1
        )
        SELECT COUNT(*) AS rows_inserted FROM upsert;
        """
        rows = await self.execute_query(query, (ingestion_run_id, json.dumps(ids_master_dict)))
        return rows[0]["rows_inserted"] if rows else 0

    async def get_mtgjson_resource_version(self) -> str | None:
        query = """
        SELECT metadata->>'version' AS version
        FROM ops.resources
        WHERE canonical_key = 'mtgjson.all_printings'
        LIMIT 1
        """
        result = await self.execute_query(query)
        return result[0].get("version") if result else None

    async def upsert_mtgjson_resource_version(self, version: str, date: str) -> None:
        query = """
        UPDATE ops.resources
        SET metadata        = jsonb_set(COALESCE(metadata, '{}'::jsonb), '{version}', to_jsonb($1::text)),
            updated_at_source = $2::timestamptz
        WHERE canonical_key = 'mtgjson.all_printings'
        """
        parsed_date = date_type.fromisoformat(date) if isinstance(date, str) else date
        await self.execute_command(query, (version, parsed_date))

    # ------------------------------------------------------------------
    # Integrity-check helpers (read-only, no side effects)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_check_rows(raw_rows: list) -> list[dict]:
        """Convert asyncpg Record objects from a check query into plain dicts.

        asyncpg surfaces JSONB columns as raw JSON strings; we parse `details`
        into a Python dict here, mirroring the pattern used in
        `update_bulk_data_uri_return_new`.
        """
        result = []
        for row in raw_rows:
            details_raw = row.get("details") if hasattr(row, "get") else row["details"]
            if isinstance(details_raw, str):
                details = json.loads(details_raw) if details_raw else {}
            elif details_raw is None:
                details = {}
            else:
                details = details_raw
            result.append(
                {
                    "check_name": row["check_name"],
                    "severity": row["severity"],
                    "row_count": row["row_count"],
                    "details": details,
                }
            )
        return result

    async def run_scryfall_run_diff(
        self, ingestion_run_id: int | None = None
    ) -> list[dict]:
        """Run the post-run diff report for the most recent (or specified) Scryfall run.

        The underlying SQL (`scryfall_run_diff.sql`) always targets the most
        recent `scryfall_daily` pipeline run via an internal CTE.  The
        `ingestion_run_id` argument is accepted for forward-compatibility but is
        **not currently forwarded to the query** — the SQL does not expose a
        bind-parameter for it.  A future migration of the SQL to accept a
        ``$1`` placeholder will make this arg functional without changing
        callers.

        Returns a list of dicts with keys:
            ``check_name`` (str), ``severity`` (str), ``row_count`` (int),
            ``details`` (dict).
        """
        raw = await self.execute_query(scryfall_run_diff_sql)
        return self._parse_check_rows(raw)

    async def run_scryfall_integrity_checks(self) -> list[dict]:
        """Run the 24-check orphan / loose-data integrity scan for the Scryfall pipeline.

        Covers ``card_catalog``, ``ops``, and ``pricing`` schemas.  All checks
        are pure SELECTs — zero side effects — safe to run from any read-only
        role.

        Returns a list of dicts with keys:
            ``check_name`` (str), ``severity`` (str), ``row_count`` (int),
            ``details`` (dict).
        """
        raw = await self.execute_query(scryfall_integrity_checks_sql)
        return self._parse_check_rows(raw)

    async def run_public_schema_leak_check(self) -> list[dict]:
        """Confirm that no app objects leaked into the ``public`` schema.

        Checks tables, views, sequences, functions, and search_path config.
        Extension-owned objects (pgvector, timescaledb) are excluded so that
        expected noise does not mask real findings.

        Returns a list of dicts with keys:
            ``check_name`` (str), ``severity`` (str), ``row_count`` (int),
            ``details`` (dict).
        """
        raw = await self.execute_query(public_schema_leak_check_sql)
        return self._parse_check_rows(raw)

    # ------------------------------------------------------------------
    # Metric-registry primitives
    # ------------------------------------------------------------------
    # Small, composable queries that the mtgstock sanity-report metrics
    # call. Every method resolves `ingestion_run_id=None` to "the most
    # recent run for this pipeline" so metric callers can stay oblivious.

    async def get_latest_run_id(self, pipeline_name: str) -> int | None:
        """Return the id of the most recent run for ``pipeline_name`` (any status)."""
        query = """
        SELECT id
        FROM ops.ingestion_runs
        WHERE pipeline_name = $1
        ORDER BY started_at DESC
        LIMIT 1
        """
        rows = await self.execute_query(query, (pipeline_name,))
        return rows[0]["id"] if rows else None

    async def fetch_run_summary(self, ingestion_run_id: int) -> dict | None:
        """Return run-level fields used by several metrics in one round-trip.

        Keys: ``status``, ``started_at``, ``ended_at``, ``duration_seconds``,
        ``current_step``, ``error_code``. ``duration_seconds`` is NULL if the
        run is still in flight.
        """
        query = """
        SELECT
            status,
            started_at,
            ended_at,
            EXTRACT(EPOCH FROM (ended_at - started_at))::float AS duration_seconds,
            current_step,
            error_code
        FROM ops.ingestion_runs
        WHERE id = $1
        """
        rows = await self.execute_query(query, (ingestion_run_id,))
        return dict(rows[0]) if rows else None

    async def fetch_step_durations(self, ingestion_run_id: int) -> dict[str, float]:
        """Return ``{step_name: duration_seconds}`` for every step of the run.

        Steps still running show ``duration_seconds = None``."""
        query = """
        SELECT
            step_name,
            EXTRACT(EPOCH FROM (ended_at - started_at))::float AS duration_seconds,
            status
        FROM ops.ingestion_run_steps
        WHERE ingestion_run_id = $1
        ORDER BY started_at
        """
        rows = await self.execute_query(query, (ingestion_run_id,))
        return {r["step_name"]: r["duration_seconds"] for r in rows}

    async def fetch_steps_failed_count(self, ingestion_run_id: int) -> int:
        query = """
        SELECT COUNT(*)::int AS n
        FROM ops.ingestion_run_steps
        WHERE ingestion_run_id = $1 AND status = 'failed'
        """
        rows = await self.execute_query(query, (ingestion_run_id,))
        return rows[0]["n"] if rows else 0

    async def fetch_bulk_folder_errors(
        self, ingestion_run_id: int, step_name: str = "bulk_load"
    ) -> int:
        """Sum of ``items_failed`` across every batch row of a given step.

        ``COALESCE`` shields against ``SUM`` returning NULL when no batch
        rows exist for the step yet."""
        query = """
        SELECT COALESCE(SUM(b.items_failed), 0)::int AS n
        FROM ops.ingestion_step_batches b
        JOIN ops.ingestion_run_steps s ON s.id = b.ingestion_run_step_id
        WHERE s.ingestion_run_id = $1 AND s.step_name = $2
        """
        rows = await self.execute_query(query, (ingestion_run_id, step_name))
        return rows[0]["n"] if rows else 0

    async def fetch_latest_successful_run_ended_at(self, pipeline_name: str):
        """Return ended_at of the most recent ingestion_runs row with status='success'
        for the given pipeline. Used by pricing freshness metrics to compute lag.
        """
        query = """
        SELECT ended_at
        FROM ops.ingestion_runs
        WHERE pipeline_name = $1 AND status = 'success' AND ended_at IS NOT NULL
        ORDER BY ended_at DESC
        LIMIT 1
        """
        rows = await self.execute_query(query, (pipeline_name,))
        return rows[0]["ended_at"] if rows else None

    async def get(self):
        raise NotImplementedError("This method is not implemented yet.")

    async def add(self):
        raise NotImplementedError("This method is not implemented yet.")

    async def update(self):
        raise NotImplementedError("This method is not implemented yet.")

    async def delete(self):
        raise NotImplementedError("This method is not implemented yet.")

    async def list(self):
        raise NotImplementedError("This method is not implemented yet.")
