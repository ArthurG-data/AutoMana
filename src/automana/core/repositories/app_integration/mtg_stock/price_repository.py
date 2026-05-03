from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository
import asyncio, io, logging
from typing import Optional

logger = logging.getLogger(__name__)

class PriceRepository(AbstractRepository):
    def __init__(self, connection, executor = None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "PriceRepository"

    async def rollback_transaction(self):
        """
        Roll back the current transaction.
        """
        try:
            await self.connection.execute("ROLLBACK;")
            logger.info("Transaction rolled back successfully.")
        except Exception as e:
            logger.error("Error rolling back transaction", extra={"error": str(e)})

    async def _copy_to_table(self, df, schema_name, table_name):
        # Serialise to CSV in a thread so the event loop stays alive during
        # what can be several minutes of CPU work on a 20M+ row DataFrame.
        # Blocking the event loop here lets asyncpg's internal pool keepalive
        # fire and reclaim the connection, causing InterfaceError on the next
        # copy_to_table call.
        def _to_csv():
            buf = io.BytesIO()
            df.to_csv(buf, index=False, header=True, encoding='utf-8')
            buf.seek(0)
            return buf

        buf = await asyncio.to_thread(_to_csv)
        # No explicit timeout: inherits conn._config.command_timeout, which
        # ServiceManager overrides per-service (3 600 s for bulk_load).
        await self.connection.copy_to_table(
            table_name=table_name,
            schema_name=schema_name,
            source=buf,
            format='csv',
            header=True,
        )

    async def call_load_stage_from_raw(
        self, source_name: str = "mtgstocks", batch_days: int = 30,
        ingestion_run_id: Optional[int] = None,
    ):
        """Call pricing.load_staging_prices_batched(source_name, batch_days, ingestion_run_id).

        `source_name` must match a row in `pricing.price_source.code`. Migration
        16 made `source_name` a required positional argument.
        When `ingestion_run_id` is provided, the procedure writes per-batch rows
        to `ops.ingestion_step_batches` and updates `ops.ingestion_run_steps.progress`."""
        # The procedure inserts into the compressed price_observation hypertable
        # via ON CONFLICT DO UPDATE. Historical chunks require decompression to
        # check for conflicts; the default limit (100 000 tuples) is exceeded on
        # every 30-day batch of historical data. Disable the guard for this
        # session-scoped bulk load, then reset so the pooled connection is clean.
        await self.connection.execute(
            "SET timescaledb.max_tuples_decompressed_per_dml_transaction = 0"
        )
        try:
            await self.connection.execute(
                "CALL pricing.load_staging_prices_batched($1::varchar, $2::int, $3::int);",
                source_name,
                batch_days,
                ingestion_run_id,
            )
        finally:
            await self.connection.execute(
                "RESET timescaledb.max_tuples_decompressed_per_dml_transaction"
            )

    async def call_resolve_price_rejects(
        self,
        limit: int = 50000,
        only_unresolved: bool = True,
    ) -> int:
        """Invoke pricing.resolve_price_rejects(p_limit, p_only_unresolved).

        Note: `resolve_price_rejects` is a FUNCTION (returns bigint), not a
        procedure — invoke with SELECT. Returns the number of reject rows
        it was able to resolve and re-feed into staging."""
        row = await self.connection.fetchrow(
            "SELECT pricing.resolve_price_rejects($1::int, $2::boolean) AS rows_resolved;",
            limit,
            only_unresolved,
        )
        return int(row["rows_resolved"] or 0) if row else 0

    async def call_load_prices_from_staging(self, batch_days: int = 30):
        """Call pricing.load_prices_from_staged_batched(batch_days).

        Promotes narrow rows from `pricing.stg_price_observation` into the
        `pricing.price_observation` hypertable. Replaces the legacy pair
        `load_dim_from_staging` + `load_prices_from_dim_batched` which were
        never created in the live DB."""
        def _on_notify(conn, pid, channel, payload):
            logger.info("DB notify", extra={"channel": channel, "payload": payload})

        try:
            await self.connection.add_listener('staging_log', _on_notify)
            await self.connection.execute(
                "CALL pricing.load_prices_from_staged_batched($1::int);",
                batch_days,
            )
            logger.info("Called load_prices_from_staged_batched()")
        finally:
            try:
                await self.connection.remove_listener('staging_log', _on_notify)
            except Exception:
                pass

    async def copy_prices(self, df):
        await self._copy_to_table(df, "pricing", "shopify_staging_raw")

    async def copy_prices_mtgstock(self, df):
        await self._copy_to_table(df, "pricing", "raw_mtg_stock_price")

    async def clear_raw_prices(self) -> int:
        """Delete all rows from the raw landing table. Returns deleted row count."""
        rows = await self.execute_query(
            "WITH del AS (DELETE FROM pricing.raw_mtg_stock_price RETURNING 1) "
            "SELECT count(*)::int AS n FROM del"
        )
        return rows[0]["n"] if rows else 0

    # ------------------------------------------------------------------
    # Metric-registry primitives
    # ------------------------------------------------------------------
    # Read-only primitives used by mtgstock sanity-report metrics. First
    # four operate on the *current state* of the pricing staging tables —
    # `raw_mtg_stock_price` has no `ingestion_run_id` column, and staging
    # tables are repopulated per-run, so "current state after the most
    # recent run" is the only meaningful run-scope here (mirrors
    # `ops.integrity.scryfall_run_diff`).

    async def fetch_raw_prints_count(self) -> int:
        """Distinct print_id count currently in `pricing.raw_mtg_stock_price`."""
        query = """
        SELECT COUNT(DISTINCT print_id)::int AS n
        FROM pricing.raw_mtg_stock_price
        """
        rows = await self.execute_query(query)
        return rows[0]["n"] if rows else 0

    async def fetch_raw_rows_count(self) -> int:
        query = """
        SELECT COUNT(*)::int AS n
        FROM pricing.raw_mtg_stock_price
        """
        rows = await self.execute_query(query)
        return rows[0]["n"] if rows else 0

    async def fetch_linked_count(self) -> int:
        """Staged rows resolved to a card_version_id."""
        query = """
        SELECT COUNT(*)::int AS n
        FROM pricing.stg_price_observation
        WHERE card_version_id IS NOT NULL
        """
        rows = await self.execute_query(query)
        return rows[0]["n"] if rows else 0

    async def fetch_rejected_count(self) -> int:
        """Rows that failed resolution and landed in the reject table.

        The reject table is lazily created inside
        `pricing.load_staging_prices_batched`, so before the mtgstock
        pipeline has ever run it may not exist. `to_regclass` returns NULL
        for a missing relation without raising — use it as a cheap probe
        instead of letting the COUNT query blow up on an unknown table.
        """
        exists_rows = await self.execute_query(
            "SELECT to_regclass('pricing.stg_price_observation_reject') IS NOT NULL AS t"
        )
        if not (exists_rows and exists_rows[0]["t"]):
            return 0

        rows = await self.execute_query(
            "SELECT COUNT(*)::int AS n FROM pricing.stg_price_observation_reject"
        )
        return rows[0]["n"] if rows else 0

    async def fetch_promoted_count(
        self, since, until, source_code: str = "mtgstocks"
    ) -> int:
        """Count rows promoted to the `price_observation` hypertable inside a
        run's wall-clock window.

        Filters on `scraped_at` (timestamptz) — not `ts_date` (business date),
        which is the date the price applies to, unrelated to when the row
        was ingested. `scraped_at` is set by `bulk_load` at insertion time.
        """
        query = """
        SELECT COUNT(*)::int AS n
        FROM pricing.price_observation po
        JOIN pricing.source_product sp ON sp.source_product_id = po.source_product_id
        JOIN pricing.price_source ps ON ps.source_id = sp.source_id
        WHERE po.scraped_at >= $1
          AND po.scraped_at <= $2
          AND ps.code = $3
        """
        rows = await self.execute_query(query, (since, until, source_code))
        return rows[0]["n"] if rows else 0

    async def fetch_max_observation_age_days(self) -> int | None:
        """Days since the most recent price_observation.ts_date across all sources."""
        query = """
        SELECT (CURRENT_DATE - MAX(ts_date))::int AS age_days
        FROM pricing.price_observation
        """
        rows = await self.execute_query(query, ())
        return rows[0]["age_days"] if rows else None

    async def fetch_per_source_lag_hours(self) -> dict[str, float | None]:
        """{source_code: hours_since_latest_observation} for every price_source."""
        query = """
        SELECT
            ps.code AS source_code,
            EXTRACT(EPOCH FROM (now() - MAX(po.created_at))) / 3600.0 AS lag_hours
        FROM pricing.price_source ps
        LEFT JOIN pricing.source_product sp ON sp.source_id = ps.source_id
        LEFT JOIN pricing.price_observation po ON po.source_product_id = sp.source_product_id
        GROUP BY ps.code
        """
        rows = await self.execute_query(query, ())
        return {r["source_code"]: r["lag_hours"] for r in rows}

    async def fetch_per_source_observation_coverage_pct(
        self, window_days: int = 30
    ) -> dict[str, float | None]:
        """{source_code: pct} where pct is fraction of source_product rows with a
        price_observation in the last ``window_days`` days."""
        query = """
        SELECT
            ps.code AS source_code,
            CASE WHEN COUNT(sp.source_product_id) = 0 THEN NULL
                 ELSE ROUND(
                     100.0 * COUNT(DISTINCT po.source_product_id)
                     / NULLIF(COUNT(DISTINCT sp.source_product_id), 0), 2
                 )::float
            END AS pct
        FROM pricing.price_source ps
        LEFT JOIN pricing.source_product sp ON sp.source_id = ps.source_id
        LEFT JOIN pricing.price_observation po
               ON po.source_product_id = sp.source_product_id
              AND po.ts_date >= CURRENT_DATE - ($1::int || ' days')::interval
        GROUP BY ps.code
        """
        rows = await self.execute_query(query, (window_days,))
        return {r["source_code"]: r["pct"] for r in rows}

    async def fetch_orphan_product_ref_mtg_count(self) -> int:
        """pricing.product_ref rows whose game_id matches the 'mtg' card_game row
        but have no pricing.mtg_card_products row."""
        query = """
        SELECT COUNT(*)::int AS n
        FROM pricing.product_ref pr
        JOIN pricing.card_game cg ON cg.game_id = pr.game_id
        WHERE cg.code = 'mtg'
          AND NOT EXISTS (
              SELECT 1 FROM pricing.mtg_card_products mcp
              WHERE mcp.product_id = pr.product_id
          )
        """
        rows = await self.execute_query(query, ())
        return rows[0]["n"] if rows else 0

    async def fetch_orphan_observation_count(self) -> int:
        """price_observation rows whose source_product_id no longer exists in
        source_product. Hard FK should make this 0."""
        query = """
        SELECT COUNT(*)::int AS n
        FROM pricing.price_observation po
        WHERE NOT EXISTS (
            SELECT 1 FROM pricing.source_product sp
            WHERE sp.source_product_id = po.source_product_id
        )
        """
        rows = await self.execute_query(query, ())
        return rows[0]["n"] if rows else 0

    async def fetch_stg_residual_count(self) -> int:
        """Estimated row count of stg_price_observation via pg_class.reltuples.
        Fast (no scan); good enough for a residual-drain alarm."""
        query = """
        SELECT reltuples::bigint AS n
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'pricing' AND c.relname = 'stg_price_observation'
        """
        rows = await self.execute_query(query, ())
        return rows[0]["n"] if rows else 0

    async def fetch_observation_pk_collision_count(self) -> int:
        """Composite-PK violations in price_observation. Should always be 0."""
        query = """
        SELECT COUNT(*)::int AS n
        FROM (
            SELECT 1
            FROM pricing.price_observation
            GROUP BY ts_date, source_product_id, price_type_id, finish_id,
                     condition_id, language_id, data_provider_id
            HAVING COUNT(*) > 1
        ) dup
        """
        rows = await self.execute_query(query, ())
        return rows[0]["n"] if rows else 0

    async def fetch_card_coverage_stats(self) -> dict:
        """Card-version-level price coverage across the full catalog.

        Returns counts for: total card versions, those with any price
        observation, those without, and the foil/nonfoil split.  Single
        round-trip via CTE to keep latency predictable on large hypertables.
        """
        query = """
        WITH
          total AS (
            SELECT COUNT(*)::int AS n FROM card_catalog.card_version
          ),
          priced AS (
            SELECT COUNT(DISTINCT mcp.card_version_id)::int AS n
            FROM pricing.mtg_card_products mcp
            WHERE EXISTS (
              SELECT 1
              FROM pricing.source_product sp
              JOIN pricing.price_observation po
                ON po.source_product_id = sp.source_product_id
              WHERE sp.product_id = mcp.product_id
            )
          ),
          nonfoil AS (
            SELECT COUNT(DISTINCT mcp.card_version_id)::int AS n
            FROM pricing.mtg_card_products mcp
            JOIN pricing.source_product sp ON sp.product_id = mcp.product_id
            JOIN pricing.price_observation po ON po.source_product_id = sp.source_product_id
            JOIN pricing.card_finished cf ON cf.finish_id = po.finish_id
            WHERE upper(cf.code) = 'NONFOIL'
          ),
          foil AS (
            SELECT COUNT(DISTINCT mcp.card_version_id)::int AS n
            FROM pricing.mtg_card_products mcp
            JOIN pricing.source_product sp ON sp.product_id = mcp.product_id
            JOIN pricing.price_observation po ON po.source_product_id = sp.source_product_id
            JOIN pricing.card_finished cf ON cf.finish_id = po.finish_id
            WHERE upper(cf.code) <> 'NONFOIL'
          )
        SELECT
          t.n   AS total_card_versions,
          p.n   AS with_price,
          t.n - p.n AS without_price,
          nf.n  AS with_nonfoil_price,
          f.n   AS with_foil_price
        FROM total t, priced p, nonfoil nf, foil f
        """
        rows = await self.execute_query(query, ())
        if not rows:
            return {
                "total_card_versions": 0,
                "with_price": 0,
                "without_price": 0,
                "with_nonfoil_price": 0,
                "with_foil_price": 0,
            }
        r = rows[0]
        return {
            "total_card_versions": r["total_card_versions"],
            "with_price": r["with_price"],
            "without_price": r["without_price"],
            "with_nonfoil_price": r["with_nonfoil_price"],
            "with_foil_price": r["with_foil_price"],
        }

    async def fetch_total_observation_count(self) -> int:
        """Estimated total row count of price_observation via pg_class.reltuples.

        Fast (no full scan); good enough for a volume alarm. Use the real
        COUNT only when exact values matter.
        """
        query = """
        SELECT reltuples::bigint AS n
        FROM pg_class c
        JOIN pg_namespace ns ON ns.oid = c.relnamespace
        WHERE ns.nspname = 'pricing' AND c.relname = 'price_observation'
        """
        rows = await self.execute_query(query, ())
        # pg_class.reltuples = -1 means the table has never been ANALYZEd; treat as 0.
        n = rows[0]["n"] if rows else 0
        return max(n, 0)

    # ------------------------------------------------------------------
    # Tier 2 / 3 health primitives
    # ------------------------------------------------------------------
    # These are fast, read-only probes used by the tier_metrics module.
    # Hypertable row counts use pg_class.reltuples (the ANALYZE estimate)
    # because COUNT(*) on a hypertable with many chunks is very slow.
    # Callers that need exact counts should add a dedicated method.

    async def fetch_tier2_row_count(self) -> int:
        """Estimated row count of pricing.print_price_daily (Tier 2).

        Uses the pg_class fast-path; same strategy as
        ``fetch_total_observation_count``.  Returns 0 if the table has never
        been ANALYZEd (reltuples == -1).
        """
        query = """
        SELECT GREATEST(reltuples, 0)::bigint AS n
        FROM pg_class c
        JOIN pg_namespace ns ON ns.oid = c.relnamespace
        WHERE ns.nspname = 'pricing' AND c.relname = 'print_price_daily'
        """
        rows = await self.execute_query(query, ())
        return int(rows[0]["n"]) if rows else 0

    async def fetch_tier3_row_count(self) -> int:
        """Estimated row count of pricing.print_price_weekly (Tier 3).

        Uses the pg_class fast-path.  Returns 0 when the table is empty or
        has never been ANALYZEd.
        """
        query = """
        SELECT GREATEST(reltuples, 0)::bigint AS n
        FROM pg_class c
        JOIN pg_namespace ns ON ns.oid = c.relnamespace
        WHERE ns.nspname = 'pricing' AND c.relname = 'print_price_weekly'
        """
        rows = await self.execute_query(query, ())
        return int(rows[0]["n"]) if rows else 0

    async def fetch_tier_sync_diff(self) -> dict[str, int]:
        """Row counts for Tier 1 and Tier 2 and their absolute difference.

        Both counts use the pg_class fast-path so the query is cheap even on
        a large hypertable.  The ``diff`` key is ``abs(tier1 - tier2)``; a
        healthy system has ``diff == 0``.

        Returns::

            {
                "tier1_rows": int,   # price_observation estimate
                "tier2_rows": int,   # print_price_daily estimate
                "diff": int,         # abs difference — 0 means in sync
            }
        """
        query = """
        SELECT
            GREATEST(
                (SELECT reltuples FROM pg_class c
                 JOIN pg_namespace ns ON ns.oid = c.relnamespace
                 WHERE ns.nspname = 'pricing' AND c.relname = 'price_observation'),
                0
            )::bigint AS tier1_rows,
            GREATEST(
                (SELECT reltuples FROM pg_class c
                 JOIN pg_namespace ns ON ns.oid = c.relnamespace
                 WHERE ns.nspname = 'pricing' AND c.relname = 'print_price_daily'),
                0
            )::bigint AS tier2_rows
        """
        rows = await self.execute_query(query, ())
        if not rows:
            return {"tier1_rows": 0, "tier2_rows": 0, "diff": 0}
        t1 = int(rows[0]["tier1_rows"])
        t2 = int(rows[0]["tier2_rows"])
        return {"tier1_rows": t1, "tier2_rows": t2, "diff": abs(t1 - t2)}

    async def fetch_archival_ready_row_count(
        self, older_than_years: int = 5
    ) -> dict[str, int | str]:
        """Rows in print_price_daily that are eligible for archive_to_weekly().

        A row is archivable when its ``price_date`` is older than
        ``older_than_years`` (default 5, matching the stored procedure
        default).  This is a real COUNT — the table is not a hypertable for
        the purpose of this range query, so it respects chunk pruning.

        Returns::

            {
                "archivable_rows": int,
                "cutoff_date": str,   # ISO date string (YYYY-MM-DD)
            }
        """
        query = """
        SELECT
            COUNT(*)::bigint           AS archivable_rows,
            (CURRENT_DATE - ($1::int || ' years')::interval)::date::text AS cutoff_date
        FROM pricing.print_price_daily
        WHERE price_date < CURRENT_DATE - ($1::int || ' years')::interval
        """
        rows = await self.execute_query(query, (older_than_years,))
        if not rows:
            return {"archivable_rows": 0, "cutoff_date": ""}
        return {
            "archivable_rows": int(rows[0]["archivable_rows"]),
            "cutoff_date": rows[0]["cutoff_date"] or "",
        }

    async def fetch_watermark_lag_days(self) -> dict[str, int | None]:
        """Days behind for each tier watermark row.

        ``daily`` freshness target: <= 1 day behind (CURRENT_DATE - 1).
        ``weekly`` is informational only — the value is NULL if the watermark
        row is still at the seed date ``1970-01-01`` (never run).

        Returns::

            {
                "daily_lag_days":  int | None,   # None → tier_watermark missing
                "weekly_lag_days": int | None,
                "daily_last_date": str | None,   # ISO date or None
                "weekly_last_date": str | None,
            }
        """
        query = """
        SELECT
            tier_name,
            last_processed_date,
            (CURRENT_DATE - last_processed_date)::int AS lag_days
        FROM pricing.tier_watermark
        ORDER BY tier_name
        """
        rows = await self.execute_query(query, ())
        result: dict[str, int | None] = {
            "daily_lag_days": None,
            "weekly_lag_days": None,
            "daily_last_date": None,
            "weekly_last_date": None,
        }
        for row in rows:
            tier = row["tier_name"]
            lag = row["lag_days"]
            last = str(row["last_processed_date"]) if row["last_processed_date"] else None
            if tier == "daily":
                # The seed date 1970-01-01 means the procedure has never run;
                # treat as NULL lag so the metric fires an error-level alert
                # rather than a misleadingly large integer.
                if last == "1970-01-01":
                    result["daily_lag_days"] = None
                else:
                    result["daily_lag_days"] = int(lag) if lag is not None else None
                result["daily_last_date"] = last
            elif tier == "weekly":
                if last == "1970-01-01":
                    result["weekly_lag_days"] = None
                else:
                    result["weekly_lag_days"] = int(lag) if lag is not None else None
                result["weekly_last_date"] = last
        return result

    def add(self):
        raise NotImplementedError("Method not implemented")

    def delete(self):
        raise NotImplementedError("Method not implemented")

    def update(self):
        raise NotImplementedError("Method not implemented")
    def get(self):
        raise NotImplementedError("Method not implemented")

    async def list(self):
        raise NotImplementedError("Method not implemented")
