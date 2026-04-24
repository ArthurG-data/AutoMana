import io
from typing import  Optional, Any
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
        result = await self.execute_command(queries.delete_card_query, card_id)
        return result is not None

    async def update(self, item):
        pass

    async def get(self,
                  card_id: UUID,
                 ) -> dict[str, Any]|None:
        # if a list
    
        query = """ SELECT uc.card_name, r.rarity_name, s.set_name,s.set_code, uc.cmc, cv.oracle_text, s.released_at, s.digital, r.rarity_name
                FROM card_catalog.unique_cards_ref uc
                JOIN card_catalog.card_version cv ON uc.unique_card_id = cv.unique_card_id
                JOIN card_catalog.rarities_ref r ON cv.rarity_id = r.rarity_id
                JOIN card_catalog.sets s ON cv.set_id = s.set_id 
                WHERE cv.card_version_id = $1;"""

        result = await self.execute_query(query, (card_id,))
        return result[0] if result else None

    async def search(
            self, 
            name: Optional[str] = None,
            color: Optional[str] = None,
            rarity: Optional[str] = None,
            set_name: Optional[str] = None,
            mana_cost: Optional[int] = None,
            digital: Optional[bool] = None,
            card_type : Optional[str] = None,
            released_after: Optional[str] = None,
            released_before: Optional[str] = None,
            limit: int = 100,
            offset: int = 0,
            sort_by: Optional[str] = "card_name",
            sort_order: Optional[str] = "asc"
    ) -> dict[str, Any]:
        conditions = []
        values = []
        counter = 1

        if name:
            conditions.append(f"uc.card_name ILIKE ${counter}")
            values.append(f"%{name}%")
            counter += 1
        if color:
            conditions.append(f"cv.color ILIKE ${counter}")
            values.append(f"%{color}%")
            counter += 1
        if rarity:
            conditions.append(f"r.rarity_name ILIKE ${counter}")
            values.append(f"%{rarity}%")
            counter += 1
        if set_name:
            conditions.append(f"s.set_name ILIKE ${counter}")
            values.append(f"%{set_name}%")
            counter += 1
        if mana_cost:
            conditions.append(f"uc.cmc = ${counter}")
            values.append(mana_cost)
            counter += 1
        if digital is not None:
            conditions.append(f"s.digital = ${counter}")
            values.append(digital)
            counter += 1

        # Add date filters if provided
        if released_after:
            conditions.append(f"s.released_at > ${counter}")
            values.append(released_after)
            counter += 1

        if released_before:
            conditions.append(f"s.released_at < ${counter}")
            values.append(released_before)
            counter += 1

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        order_clause = f"ORDER BY {sort_by} {sort_order.upper()}"

        query = f""" SELECT uc.card_name, r.rarity_name, s.set_name,s.set_code, uc.cmc, cv.oracle_text, s.released_at, s.digital, r.rarity_name
                FROM card_catalog.unique_cards_ref uc
                JOIN card_catalog.card_version cv ON uc.unique_card_id = cv.unique_card_id
                JOIN card_catalog.rarities_ref r ON cv.rarity_id = r.rarity_id
                JOIN card_catalog.sets s ON cv.set_id = s.set_id
                {where_clause}
                {order_clause}
                LIMIT ${counter} OFFSET ${counter + 1}
        """
        values.extend([limit, offset])
        cards = await self.execute_query(query, tuple(values))

        count_query = f""" SELECT COUNT(*) as total_count FROM card_catalog.unique_cards_ref uc
                JOIN card_catalog.card_version cv ON uc.unique_card_id = cv.unique_card_id
                JOIN card_catalog.rarities_ref r ON cv.rarity_id = r.rarity_id
                JOIN card_catalog.sets s ON cv.set_id = s.set_id
                {where_clause}
        """
        count_values = values[:-2]
        count_result = await self.execute_query(count_query, tuple(count_values))
        total_count = count_result[0]["total_count"] if count_result else 0
        return {
            "cards": cards,
            "total_count": total_count
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
        """Outcome of a single-row ``card_external_identifier`` upsert attempt.

        Carries enough signal for the service layer to decide which domain
        exception to raise (or to return ``inserted`` unchanged).

        Attributes:
            ref_found: ``True`` iff ``identifier_name`` resolved to a row in
                ``card_catalog.card_identifier_ref``.
            card_version_exists: ``True`` iff ``card_version_id`` exists in
                ``card_catalog.card_version``.
            inserted: ``True`` iff a new row was actually written; ``False``
                for an ON CONFLICT DO NOTHING no-op OR for the degenerate
                case where either lookup above failed (the INSERT ... SELECT
                produces zero rows when either CTE is empty).
        """
        ref_found: bool
        card_version_exists: bool
        inserted: bool

    async def register_external_identifier(
        self,
        card_version_id: UUID,
        identifier_name: str,
        value: str,
    ) -> "CardReferenceRepository.ExternalIdentifierRegistration":
        """Idempotently register one (card_version, identifier) pair.

        Single-CTE round-trip to avoid a check-then-insert race: the ref
        lookup, card_version existence probe, and upsert all happen in one
        query. Mirrors the JOIN-with-ref pattern used by
        ``insert_full_card_version`` in 02_card_schema.sql (lines 734–747),
        adapted for a single row.

        Conflict target is the ``(card_version_id, card_identifier_ref_id)``
        primary key — this is the "same identifier already registered for
        this card_version" case and is the intended no-op.

        The secondary ``UNIQUE (card_identifier_ref_id, value)`` constraint
        is *not* absorbed by this ON CONFLICT clause. If the same
        ``(identifier_name, value)`` pair is already attached to a different
        ``card_version_id``, the INSERT will raise and the service layer
        will translate it to ``CardInsertError``. That is the correct
        behavior: external IDs like scryfall_id are supposed to be globally
        unique per card_version, so a collision indicates genuinely
        inconsistent input, not idempotent re-entry.

        Args:
            card_version_id: Target card_version primary key.
            identifier_name: Symbolic name in ``card_identifier_ref``
                (e.g. ``"scryfall_id"``, ``"tcgplayer_id"``).
            value: The raw identifier value as stored by the upstream source.

        Returns:
            ExternalIdentifierRegistration with three booleans the service
            uses to decide between returning ``inserted`` and raising a
            domain exception.
        """
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
            # The SELECT above always returns exactly one row. Getting here
            # means the driver layer misbehaved — surface loudly rather than
            # silently reporting "nothing happened".
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
