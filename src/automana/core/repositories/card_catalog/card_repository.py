import io
from datetime import date
from typing import Optional, Any, Dict
from uuid import UUID
from dataclasses import dataclass, field

from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository
from automana.core.repositories.card_catalog import card_queries as queries

class CardReferenceRepository(AbstractRepository[Any]):
    def __init__(self, connection, executor = None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "CardRepository"
    
    async def add(self, value : tuple) -> UUID|None:
       row = await self.execute_command(queries.insert_full_card_query, value)
       return row

    @dataclass(slots=True)
    class BatchInsertResponse:
        total_processed: int
        successful_inserts: int
        failed_inserts: int
        success_rate: float = field(init=False)
        inserted_card_ids: list[UUID]
        errors: list[str]

        def __post_init__(self)->None:
            self.success_rate = (
                self.successful_inserts / self.total_processed * 100
                if self.total_processed > 0
                else 0
            )

    async def _copy_csv_to_table(self, buffer :bytes, schema_name, table_name):
        data = buffer.getvalue()  # convert BytesIO -> bytes
        data_mv = memoryview(data)
        assert isinstance(data, (bytes, bytearray)), type(data_mv)
        status =await self.connection.copy_to_table(
            table_name=table_name,
            schema_name=schema_name,
            source=data_mv,
            format='csv',
            null='',
            delimiter='\t',
            header=False
        )
        return status

        
    async def add_many(self, values):
        #not async anymore
        result = await self.execute_query("SELECT * FROM card_catalog.insert_batch_card_versions($1::JSONB)", (values,))
        batch_result = result[0] if result else {}

        def _parse_jsonb(val, default):
            # asyncpg returns jsonb columns as raw JSON strings — parse to Python object
            if isinstance(val, str):
                import json
                return json.loads(val)
            return val if val is not None else default

        response = CardReferenceRepository.BatchInsertResponse(
            total_processed=batch_result.get('total_processed', 0),
            successful_inserts=batch_result.get('successful_inserts', 0),
            failed_inserts=batch_result.get('failed_inserts', 0),
            inserted_card_ids=_parse_jsonb(batch_result.get('inserted_card_ids'), []),
            errors=_parse_jsonb(batch_result.get('error_details'), [])
        )
        return response

    async def delete(self, card_id: UUID):
        rows = await self.execute_query(queries.delete_card_query, (card_id,))
        return len(rows) > 0

    async def update(self, item):
        pass

    async def get(self,
                  card_id: UUID,
                 ) -> dict[str, Any]|None:
        # if a list

        query = """ SELECT cv.card_version_id, uc.card_name, r.rarity_name, s.set_name, s.set_code, uc.cmc, cv.oracle_text, s.released_at, s.digital, r.rarity_name,
                           ill.image_uris->>'large' AS image_large
                FROM card_catalog.unique_cards_ref uc
                JOIN card_catalog.card_version cv ON uc.unique_card_id = cv.unique_card_id
                JOIN card_catalog.rarities_ref r ON cv.rarity_id = r.rarity_id
                JOIN card_catalog.sets s ON cv.set_id = s.set_id
                LEFT JOIN card_catalog.card_version_illustration cvi ON cvi.card_version_id = cv.card_version_id
                LEFT JOIN card_catalog.illustrations ill ON ill.illustration_id = cvi.illustration_id
                WHERE cv.card_version_id = $1;"""

        result = await self.execute_query(query, (card_id,))
        return result[0] if result else None

    async def suggest(self, query: str, limit: int = 10) -> list[dict]:
        sql = """
            SELECT v.card_version_id, v.card_name, v.set_code, v.rarity_name,
                   cv.collector_number,
                   cei.value AS scryfall_id,
                   word_similarity($1, v.card_name) AS score
            FROM card_catalog.v_card_name_suggest v
            JOIN card_catalog.card_version cv ON cv.card_version_id = v.card_version_id
            LEFT JOIN card_catalog.card_external_identifier cei
                ON cei.card_version_id = v.card_version_id AND cei.card_identifier_ref_id = 1
            WHERE $1 % v.card_name
            ORDER BY score DESC
            LIMIT $2
        """
        rows = await self.execute_query(sql, (query, limit))
        return [dict(r) for r in rows]

    async def get_version_by_scryfall_id(self, scryfall_id: str) -> Optional[dict]:
        sql = """
            SELECT cv.card_version_id, uc.card_name, s.set_code, cv.collector_number
            FROM card_catalog.card_external_identifier cei
            JOIN card_catalog.card_version cv ON cv.card_version_id = cei.card_version_id
            JOIN card_catalog.unique_cards_ref uc ON uc.unique_card_id = cv.unique_card_id
            JOIN card_catalog.sets s ON s.set_id = cv.set_id
            WHERE cei.card_identifier_ref_id = 1 AND cei.value = $1
        """
        rows = await self.execute_query(sql, (scryfall_id,))
        return dict(rows[0]) if rows else None

    async def get_version_by_set_collector(self, set_code: str, collector_number: str) -> Optional[dict]:
        sql = """
            SELECT cv.card_version_id, uc.card_name, s.set_code, cv.collector_number
            FROM card_catalog.card_version cv
            JOIN card_catalog.sets s ON s.set_id = cv.set_id
            JOIN card_catalog.unique_cards_ref uc ON uc.unique_card_id = cv.unique_card_id
            WHERE s.set_code = $1 AND cv.collector_number = $2
        """
        rows = await self.execute_query(sql, (set_code, collector_number))
        return dict(rows[0]) if rows else None

    async def search(
            self,
            name: Optional[str] = None,
            color: Optional[str] = None,
            rarity: Optional[str] = None,
            set_name: Optional[str] = None,
            mana_cost: Optional[int] = None,
            digital: Optional[bool] = None,
            card_type: Optional[str] = None,
            released_after: Optional[str] = None,
            released_before: Optional[str] = None,
            oracle_text: Optional[str] = None,
            format: Optional[str] = None,
            layout: Optional[str] = None,
            limit: int = 100,
            offset: int = 0,
            sort_by: Optional[str] = "card_name",
            sort_order: Optional[str] = "asc",
    ) -> dict[str, Any]:
        """Search card versions using the v_card_versions_complete materialized view.

        Filters are ANDed together. When ``name`` or ``oracle_text`` are provided
        the result is ranked by relevance; otherwise the ``sort_by`` / ``sort_order``
        pair controls ordering.

        Notes:
            - ``color`` matches against ``color_identity`` (text[]) stored as
              proper-cased colour names (e.g. 'White', 'Blue'). Callers must
              pass the value in that casing.
            - ``card_type`` matches against the ``types`` array (e.g. 'Creature').
            - ``digital`` uses the per-card-version ``is_digital`` flag, not the
              legacy per-set ``sets.digital`` column.
            - ``released_after`` / ``released_before`` are satisfied via a JOIN to
              ``card_catalog.sets`` because ``v_card_versions_complete`` does not
              project ``released_at``.
        """
        conditions: list[str] = []
        values: list[Any] = []
        counter = 1

        # Track placeholder indices for relevance ORDER BY reuse —
        # the same $N bound in WHERE is referenced again in ORDER BY without
        # appending a duplicate value.
        name_param_idx: Optional[int] = None
        oracle_param_idx: Optional[int] = None

        if name:
            conditions.append(f"word_similarity(${counter}, v.card_name) > 0.3")
            values.append(name)
            name_param_idx = counter
            counter += 1

        if color:
            # color_identity is text[]; caller must use canonical casing (e.g. 'White').
            conditions.append(f"${counter} = ANY(v.color_identity)")
            values.append(color)
            counter += 1

        if rarity:
            conditions.append(f"v.rarity_name ILIKE ${counter}")
            values.append(f"%{rarity}%")
            counter += 1

        if set_name:
            conditions.append(f"v.set_name ILIKE ${counter}")
            values.append(f"%{set_name}%")
            counter += 1

        if mana_cost is not None:
            conditions.append(f"v.cmc = ${counter}")
            values.append(mana_cost)
            counter += 1

        if digital is not None:
            # v.is_digital is the per-card-version flag (differs from the old s.digital set-level flag).
            conditions.append(f"v.is_digital = ${counter}")
            values.append(digital)
            counter += 1

        if released_after:
            conditions.append(f"s.released_at > ${counter}")
            values.append(released_after)
            counter += 1

        if released_before:
            conditions.append(f"s.released_at < ${counter}")
            values.append(released_before)
            counter += 1

        if card_type:
            # types is text[]; caller must use canonical casing (e.g. 'Creature').
            conditions.append(f"${counter} = ANY(v.types)")
            values.append(card_type)
            counter += 1

        if oracle_text:
            conditions.append(f"v.search_vector @@ websearch_to_tsquery('english', ${counter})")
            values.append(oracle_text)
            oracle_param_idx = counter
            counter += 1

        if format:
            conditions.append(f"v.legalities->>${counter} = 'legal'")
            values.append(format)
            counter += 1

        if layout:
            conditions.append(f"v.layout_name = ${counter}")
            values.append(layout)
            counter += 1
        else:
            # Default: exclude tokens when no layout filter is specified
            conditions.append("v.layout_name NOT IN ('token', 'double_faced_token')")

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        # Dynamic ORDER BY: prefer relevance when text search params are present.
        if name_param_idx and oracle_param_idx:
            order_clause = (
                f"ORDER BY ("
                f"word_similarity(${name_param_idx}, v.card_name) + "
                f"ts_rank_cd(v.search_vector, websearch_to_tsquery('english', ${oracle_param_idx}))"
                f") DESC"
            )
        elif name_param_idx:
            order_clause = f"ORDER BY word_similarity(${name_param_idx}, v.card_name) DESC"
        elif oracle_param_idx:
            order_clause = (
                f"ORDER BY ts_rank_cd(v.search_vector, "
                f"websearch_to_tsquery('english', ${oracle_param_idx})) DESC"
            )
        else:
            safe_sort_by = sort_by if sort_by in {
                "card_name", "cmc", "rarity_name", "set_name", "set_code"
            } else "card_name"
            safe_sort_order = "DESC" if (sort_order or "").upper() == "DESC" else "ASC"
            order_clause = f"ORDER BY v.{safe_sort_by} {safe_sort_order}"

        # JOIN sets for released_at (not projected by the view) and to filter on date range.
        from_clause = (
            "FROM card_catalog.v_card_versions_complete v"
            " JOIN card_catalog.sets s ON s.set_id = v.set_id"
            " LEFT JOIN card_catalog.card_version_illustration cvi ON cvi.card_version_id = v.card_version_id"
            " LEFT JOIN card_catalog.illustrations ill ON ill.illustration_id = cvi.illustration_id"
        )

        query = f"""
            SELECT
                v.card_version_id,
                v.card_name,
                v.rarity_name,
                v.set_name,
                v.set_code,
                v.cmc,
                v.oracle_text,
                v.is_digital AS digital,
                s.released_at,
                ill.image_uris->>'normal' AS image_normal
            {from_clause}
            {where_clause}
            {order_clause}
            LIMIT ${counter} OFFSET ${counter + 1}
        """
        values.extend([limit, offset])
        cards = await self.execute_query(query, tuple(values))

        count_query = f"""
            SELECT COUNT(*) AS total_count
            {from_clause}
            {where_clause}
        """
        count_values = values[:-2]
        count_result = await self.execute_query(count_query, tuple(count_values))
        total_count = count_result[0]["total_count"] if count_result else 0
        return {
            "cards": cards,
            "total_count": total_count,
        }
    async def list(self) -> dict[str, Any]:
        raise NotImplementedError("Method not implemented")


    def bulk_update_mtg_stock_ids(self, ids: dict[str, str]):
        #not async anymore
        if not ids:
            return 0  # or just return

        # build two parallel arrays
        scry_ids = list(ids.keys())
        stock_ids = list(ids.values())

        query = """
        WITH ids AS (
            SELECT
                (SELECT card_identifier_ref_id FROM card_identifier_ref WHERE identifier_name = 'scryfall_id')  AS scry_ref,
                (SELECT card_identifier_ref_id FROM card_identifier_ref WHERE identifier_name = 'mtg_stock_id') AS stock_ref
        ),
        data(scryfall_id, mtgstock_id) AS (
            SELECT * FROM unnest($1::TEXT[], $2::TEXT[])  -- zipped pairs
        )
        INSERT INTO card_external_identifier (card_identifier_ref_id, card_version_id, value)
        SELECT
            ids.stock_ref,                -- we are INSERTING mtg_stock_id ...
            cei.card_version_id,
            data.mtgstock_id
        FROM data
        CROSS JOIN ids
        JOIN card_external_identifier AS cei
        ON cei.card_identifier_ref_id = ids.scry_ref  -- ... using scryfall to resolve card_version
        AND cei.value::TEXT             = data.scryfall_id
        ON CONFLICT (card_identifier_ref_id, card_version_id)
        DO UPDATE SET value = EXCLUDED.value;
        """

        # Pass TWO params, not one
        self.execute_command(query,(scry_ids, stock_ids))

    @dataclass(slots=True, frozen=True)
    class ExternalIdentifierRegistration:
        """Outcome of a single-row card_external_identifier upsert."""
        ref_found: bool
        card_version_exists: bool
        inserted: bool

    async def register_external_identifier(
        self,
        card_version_id: UUID,
        identifier_name: str,
        value: str,
    ) -> "CardReferenceRepository.ExternalIdentifierRegistration":
        """Idempotently register one (card_version, identifier_name, value) row via a single-CTE round-trip."""
        # ON CONFLICT targets the PK only. There is no UNIQUE (ref_id, value)
        # constraint — it was intentionally dropped so that shared identifiers
        # like tcgplayer_id and cardmarket_id can be owned by multiple
        # card_version rows (foil/non-foil pairs of the same physical product).
        # A duplicate (card_version_id, ref_id) row is silently absorbed; any
        # other combination inserts a new row, which is the correct behaviour.
        query = """
            WITH ref AS (
                SELECT card_identifier_ref_id
                FROM card_catalog.card_identifier_ref
                WHERE identifier_name = $2
            ),
            cv AS (
                SELECT card_version_id
                FROM card_catalog.card_version
                WHERE card_version_id = $1
            ),
            ins AS (
                INSERT INTO card_catalog.card_external_identifier (
                    card_version_id, card_identifier_ref_id, value
                )
                SELECT cv.card_version_id, ref.card_identifier_ref_id, $3
                FROM cv, ref
                ON CONFLICT (card_version_id, card_identifier_ref_id) DO NOTHING
                RETURNING 1
            )
            SELECT
                (SELECT card_identifier_ref_id FROM ref) IS NOT NULL AS ref_found,
                (SELECT card_version_id FROM cv)         IS NOT NULL AS card_version_exists,
                EXISTS (SELECT 1 FROM ins)                           AS inserted
        """
        rows = await self.execute_query(query, card_version_id, identifier_name, value)
        row = rows[0] if rows else None
        if row is None:
            raise RuntimeError(
                "register_external_identifier: expected one result row, got none"
            )
        return CardReferenceRepository.ExternalIdentifierRegistration(
            ref_found=bool(row["ref_found"]),
            card_version_exists=bool(row["card_version_exists"]),
            inserted=bool(row["inserted"]),
        )

    async def copy_migrations(self, buffer):
        """
        Bulk-load Scryfall migration records into ``card_catalog.scryfall_migration``
        with idempotent semantics on the ``id`` primary key.

        PostgreSQL ``COPY`` is a raw bulk transport — it has no ``ON CONFLICT``
        clause. Copying straight into the target table would blow up on the
        second daily run the moment a duplicate ``id`` shows up. The correct
        fix lives at the I/O boundary that actually knows about the conflict,
        not in a retry flag on the Celery task.

        Pattern: **COPY-into-staging + INSERT … ON CONFLICT DO NOTHING**
        (a narrow application of the Unit of Work pattern).

            1. Open a transaction so staging DDL, COPY, and the promotion
               INSERT form a single atomic unit — on failure nothing leaks.
            2. ``CREATE TEMP TABLE … ON COMMIT DROP`` — session-scoped,
               self-cleaning on COMMIT. No housekeeping, no cross-run
               collision if asyncpg reuses the connection.
            3. COPY the TSV buffer into the temp table (fast path preserved).
            4. Promote with ``INSERT … SELECT … ON CONFLICT (id) DO NOTHING``
               so duplicates on re-run are a silent no-op — not a 500.

        The staging schema mirrors ``card_catalog.scryfall_migration`` *without*
        the PK so COPY never rejects a row mid-stream; the PK check happens
        at promotion time, where ``ON CONFLICT`` can absorb it cleanly.

        A "SELECT-then-INSERT" guard would be the wrong alternative: it's
        both racy under concurrent pipeline runs and strictly slower than
        letting the DB's conflict machinery do its job.
        """
        # Keep the staging columns aligned with the tab-separated line built
        # by ``ScryfallAPIRepository.migrations_to_bytes_buffer``:
        #   id, uri, performed_at, migration_strategy,
        #   old_scryfall_id, new_scryfall_id, note, created_at, updated_at
        staging_table = "tmp_scryfall_migration_stage"

        create_staging_sql = f"""
            CREATE TEMP TABLE IF NOT EXISTS {staging_table} (
                id                 uuid,
                uri                text,
                performed_at       date,
                migration_strategy text,
                old_scryfall_id    uuid,
                new_scryfall_id    uuid,
                note               text,
                created_at         timestamptz,
                updated_at         timestamptz
            ) ON COMMIT DROP
        """

        promote_sql = f"""
            INSERT INTO card_catalog.scryfall_migration (
                id, uri, performed_at, migration_strategy,
                old_scryfall_id, new_scryfall_id, note,
                created_at, updated_at
            )
            SELECT
                id, uri, performed_at, migration_strategy,
                old_scryfall_id, new_scryfall_id, note,
                created_at, updated_at
            FROM {staging_table}
            ON CONFLICT (id) DO NOTHING
        """

        data = buffer.getvalue()  # BytesIO -> bytes
        assert isinstance(data, (bytes, bytearray)), type(data)
        data_mv = memoryview(data)

        # Single transaction binds DDL + COPY + INSERT. If any step raises,
        # asyncpg rolls back; ``ON COMMIT DROP`` guarantees the temp table
        # evaporates on the happy path — no explicit DROP required.
        async with self.connection.transaction():
            await self.connection.execute(create_staging_sql)
            copy_status = await self.connection.copy_to_table(
                table_name=staging_table,
                source=data_mv,
                format="csv",
                null="",
                delimiter="\t",
                header=False,
            )
            insert_status = await self.connection.execute(promote_sql)

        # Return both statuses — ``insert_status`` (e.g. "INSERT 0 N") is what
        # callers actually care about: rows that survived the conflict filter.
        # ``copy_status`` only reflects ingestion into the throwaway staging
        # table and is kept for observability/debugging.
        return {"copy_status": copy_status, "insert_status": insert_status}

    async def fetch_identifier_coverage_pct(self, identifier_name: str) -> dict | None:
        """Return per-identifier coverage stats for the card_catalog.identifier_coverage.* metrics.

        Returns ``{'covered': int, 'total': int, 'pct': float|None}``. ``pct`` is
        NULL when ``total`` is 0 — the metric layer treats NULL as Severity.WARN
        rather than silently passing.
        """
        query = """
        WITH totals AS (
            SELECT COUNT(*)::int AS total FROM card_catalog.card_version
        ),
        covered AS (
            SELECT COUNT(DISTINCT cei.card_version_id)::int AS covered
            FROM card_catalog.card_external_identifier cei
            JOIN card_catalog.card_identifier_ref cir
              ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
            WHERE cir.identifier_name = $1
        )
        SELECT
            covered,
            total,
            CASE WHEN total = 0 THEN NULL
                 ELSE ROUND(100.0 * covered / total, 2)::float
            END AS pct
        FROM totals, covered
        """
        rows = await self.execute_query(query, (identifier_name,))
        return dict(rows[0]) if rows else None

    async def fetch_identifier_coverage_pct_by_unique_card(
        self, identifier_name: str
    ) -> dict | None:
        """Coverage measured against ``unique_cards_ref`` rather than ``card_version``.

        Use this for identifiers that are a property of the *abstract card* (one
        value per ``unique_card_id``) rather than per-printing — most notably
        ``oracle_id``. Because ``oracle_id`` is shared across every printing of
        the same abstract card, counting rows per ``card_version`` would
        under-report coverage by the average reprint rate (~3x for oracle_id),
        making the per-``card_version`` metric misleading for these identifiers.
        Note: the ``UNIQUE (card_identifier_ref_id, value)`` constraint no longer
        exists; multiple ``card_version`` rows can legally share one oracle_id value.

        Returns the same shape as :meth:`fetch_identifier_coverage_pct`:
        ``{'covered': int, 'total': int, 'pct': float|None}``. ``covered`` is
        the count of distinct ``unique_card_id`` values for which at least one
        ``card_version`` has a row of ``identifier_name`` in
        ``card_external_identifier``; ``total`` is the count of
        ``unique_cards_ref`` rows.
        """
        query = """
        WITH totals AS (
            SELECT COUNT(*)::int AS total FROM card_catalog.unique_cards_ref
        ),
        covered AS (
            SELECT COUNT(DISTINCT cv.unique_card_id)::int AS covered
            FROM card_catalog.card_external_identifier cei
            JOIN card_catalog.card_identifier_ref cir
              ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
            JOIN card_catalog.card_version cv
              ON cv.card_version_id = cei.card_version_id
            WHERE cir.identifier_name = $1
        )
        SELECT
            covered,
            total,
            CASE WHEN total = 0 THEN NULL
                 ELSE ROUND(100.0 * covered / total, 2)::float
            END AS pct
        FROM totals, covered
        """
        rows = await self.execute_query(query, (identifier_name,))
        return dict(rows[0]) if rows else None

    async def fetch_identifier_value_count(self, identifier_name: str) -> int:
        """COUNT of card_version rows that have at least one row for ``identifier_name``.

        Used by the informational metrics (multiverse_id, tcgplayer_etched_id)
        which track raw counts rather than coverage percentages.
        """
        query = """
        SELECT COUNT(DISTINCT cei.card_version_id)::int AS n
        FROM card_catalog.card_external_identifier cei
        JOIN card_catalog.card_identifier_ref cir
          ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
        WHERE cir.identifier_name = $1
        """
        rows = await self.execute_query(query, (identifier_name,))
        return rows[0]["n"] if rows else 0

    async def fetch_identifier_audit_counts(self) -> "list[dict]":
        """Per-identifier aggregate counts for the scryfall-vs-db audit service.

        One row per ``identifier_name`` registered in ``card_identifier_ref``.
        Identifiers with zero stored rows still appear (LEFT JOIN), so the audit
        can flag them.
        """
        query = """
        SELECT
            cir.identifier_name                               AS identifier_name,
            COUNT(cei.value)::int                             AS total_rows,
            COUNT(DISTINCT cei.value)::int                    AS distinct_values,
            COUNT(DISTINCT cei.card_version_id)::int          AS distinct_card_versions,
            COUNT(DISTINCT cv.unique_card_id)::int            AS distinct_unique_cards
        FROM card_catalog.card_identifier_ref cir
        LEFT JOIN card_catalog.card_external_identifier cei
               ON cei.card_identifier_ref_id = cir.card_identifier_ref_id
        LEFT JOIN card_catalog.card_version cv
               ON cv.card_version_id = cei.card_version_id
        GROUP BY cir.identifier_name
        ORDER BY cir.identifier_name
        """
        rows = await self.execute_query(query, ())
        return [dict(r) for r in rows]

    async def fetch_card_universe_counts(self) -> dict:
        """Denominator counts used by the scryfall-vs-db audit service."""
        query = """
        SELECT
            (SELECT COUNT(*)::int FROM card_catalog.card_version)      AS total_card_versions,
            (SELECT COUNT(*)::int FROM card_catalog.unique_cards_ref)  AS total_unique_cards
        """
        rows = await self.execute_query(query, ())
        return dict(rows[0]) if rows else {"total_card_versions": 0, "total_unique_cards": 0}

    async def fetch_orphan_unique_cards_count(self) -> int:
        """COUNT of unique_cards_ref rows with zero card_version children.

        Small counts are benign (tokens / emblems not yet printed); large
        counts indicate a mid-run set-ingest stall.
        """
        query = """
        SELECT COUNT(*)::int AS n
        FROM card_catalog.unique_cards_ref ucr
        WHERE NOT EXISTS (
            SELECT 1 FROM card_catalog.card_version cv
            WHERE cv.unique_card_id = ucr.unique_card_id
        )
        """
        rows = await self.execute_query(query, ())
        return rows[0]["n"] if rows else 0

    async def fetch_external_id_value_collisions(self) -> int:
        """COUNT of (card_identifier_ref_id, value) tuples shared by more than one
        card_version_id for identifiers that upstream guarantees are per-printing unique.

        The ``UNIQUE (card_identifier_ref_id, value)`` constraint was dropped intentionally
        to allow tcgplayer_id, cardmarket_id, and tcgplayer_etched_id to be shared by
        foil/non-foil (or ★/non-★) pairs of the same physical product.  Identifiers that
        are strictly one-per-printing — ``scryfall_id``, ``multiverse_id``, ``mtgjson_id``
        — should never collide.  Any non-zero count here indicates a real bug: either a
        duplicate ingest, a pipeline retry that produced duplicate rows, or an upstream
        data error that slipped past validation.

        Identifiers intentionally excluded (expected multi-card_version sharing):
        - oracle_id           — one value per abstract card, shared across all printings
        - tcgplayer_id        — one product per physical SKU; foil/non-foil pairs share
        - cardmarket_id       — same sharing pattern as tcgplayer_id
        - tcgplayer_etched_id — Secret Lair ★ variants share the same etched product ID
                                as the base variant (confirmed upstream behavior, not a bug)
        """
        query = """
        SELECT COUNT(*)::int AS n
        FROM (
            SELECT cei.card_identifier_ref_id, cei.value
            FROM card_catalog.card_external_identifier cei
            JOIN card_catalog.card_identifier_ref cir
              ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
            WHERE cir.identifier_name IN (
                'scryfall_id', 'multiverse_id', 'mtgjson_id'
            )
            GROUP BY cei.card_identifier_ref_id, cei.value
            HAVING COUNT(DISTINCT cei.card_version_id) > 1
        ) dup
        """
        rows = await self.execute_query(query, ())
        return rows[0]["n"] if rows else 0

    async def get_price_history(
        self,
        card_version_id: UUID,
        start_date: date,
        end_date: date,
        finish: Optional[str] = None,
        aggregation: str = 'daily',
    ) -> Dict[str, Any]:
        """
        Fetch aggregated price history for a card across all sources.

        Args:
            card_version_id: Card version ID
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            finish: Optional finish code string ('NONFOIL', 'FOIL', 'ETCHED', etc.)
            aggregation: 'daily' or 'weekly' aggregation (default='daily')

        Returns:
            Dict with keys: list_avg, sold_avg, dates
            - list_avg: List[Optional[float]] with one entry per period (null-filled for missing data)
            - sold_avg: List[Optional[float]] with one entry per period (null-filled for missing data)
            - dates: List[date] with period start dates in order
        """
        finish_filter = ""
        params: list = [card_version_id, start_date, end_date]
        if finish:
            finish_filter = f"AND f.code = ${len(params) + 1}"
            params.append(finish.upper())

        if aggregation == 'weekly':
            query = f"""
            WITH weekly_range AS (
                SELECT generate_series(date_trunc('week', $2::date)::date, $3::date, interval '1 week')::date AS week_start
            ),
            tier2_prices AS (
                SELECT
                    date_trunc('week', ppd.price_date)::date AS week_start,
                    AVG(ppd.list_avg_cents)::float / 100 AS list_avg_price,
                    AVG(ppd.sold_avg_cents)::float / 100 AS sold_avg_price
                FROM pricing.print_price_daily ppd
                JOIN pricing.card_finished f ON f.finish_id = ppd.finish_id
                WHERE ppd.card_version_id = $1
                  AND ppd.price_date >= $2
                  AND ppd.price_date <= $3
                  {finish_filter}
                GROUP BY date_trunc('week', ppd.price_date)
            ),
            tier3_prices AS (
                SELECT
                    ppw.price_week AS week_start,
                    AVG(ppw.list_avg_cents)::float / 100 AS list_avg_price,
                    AVG(ppw.sold_avg_cents)::float / 100 AS sold_avg_price
                FROM pricing.print_price_weekly ppw
                JOIN pricing.card_finished f ON f.finish_id = ppw.finish_id
                WHERE ppw.card_version_id = $1
                  AND ppw.price_week >= $2
                  AND ppw.price_week <= $3
                  {finish_filter}
                GROUP BY ppw.price_week
            ),
            combined AS (
                SELECT week_start, list_avg_price, sold_avg_price FROM tier2_prices
                UNION ALL
                SELECT t3.week_start, t3.list_avg_price, t3.sold_avg_price
                FROM tier3_prices t3
                WHERE t3.week_start NOT IN (SELECT week_start FROM tier2_prices)
            )
            SELECT
                wr.week_start AS price_date,
                c.list_avg_price,
                c.sold_avg_price
            FROM weekly_range wr
            LEFT JOIN combined c ON wr.week_start = c.week_start
            ORDER BY wr.week_start ASC
            """
        else:
            query = f"""
            WITH date_range AS (
                SELECT generate_series($2::date, $3::date, interval '1 day')::date AS price_date
            ),
            daily_prices AS (
                SELECT
                    ppd.price_date,
                    AVG(ppd.list_avg_cents)::float / 100 AS list_avg_price,
                    AVG(ppd.sold_avg_cents)::float / 100 AS sold_avg_price
                FROM pricing.print_price_daily ppd
                JOIN pricing.card_finished f ON f.finish_id = ppd.finish_id
                WHERE ppd.card_version_id = $1
                  AND ppd.price_date >= $2
                  AND ppd.price_date <= $3
                  {finish_filter}
                GROUP BY ppd.price_date
            )
            SELECT
                dr.price_date,
                dp.list_avg_price,
                dp.sold_avg_price
            FROM date_range dr
            LEFT JOIN daily_prices dp ON dr.price_date = dp.price_date
            ORDER BY dr.price_date ASC
            """

        rows = await self.execute_query(query, tuple(params))

        if not rows:
            return {
                "list_avg": [],
                "sold_avg": [],
                "dates": []
            }

        list_avg = [row["list_avg_price"] for row in rows]
        sold_avg = [row["sold_avg_price"] for row in rows]
        dates = [row["price_date"] for row in rows]

        return {
            "list_avg": list_avg,
            "sold_avg": sold_avg,
            "dates": dates
        }
