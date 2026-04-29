from typing import Any, Iterable, Sequence

from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository


# Columns we COPY into, in the exact order the streamer emits them.
_STAGING_COLUMNS: tuple[str, ...] = (
    "card_uuid",
    "price_source",
    "price_type",
    "finish_type",
    "currency",
    "price_value",
    "price_date",
)


class MtgjsonRepository(AbstractRepository):

    @property
    def name(self) -> str:
        return "MtgjsonRepository"

    # ------------------------------------------------------------------ #
    # Streaming ingest                                                    #
    # ------------------------------------------------------------------ #

    async def acquire_streaming_lock(
        self, lock_name: str = "mtgjson_stream_to_staging"
    ) -> None:
        """Block until we hold the transaction-scoped advisory lock.

        Serializes concurrent streamers on this connection's transaction
        without any external locking infrastructure. Released automatically
        on COMMIT/ROLLBACK.
        """
        await self.connection.execute(
            "SELECT pg_advisory_xact_lock(hashtext($1))", lock_name
        )

    async def copy_staging_batch(self, records: Sequence[tuple]) -> int:
        """Bulk-load a batch of price rows via asyncpg ``COPY``.

        Each record must match ``_STAGING_COLUMNS`` exactly. Returns the
        number of rows handed to Postgres (not a rowcount from the server —
        asyncpg does not surface one for COPY).
        """
        if not records:
            return 0
        await self.connection.copy_records_to_table(
            "mtgjson_card_prices_staging",
            records=records,
            columns=_STAGING_COLUMNS,
            schema_name="pricing",
        )
        return len(records)

    async def upsert_mtgjson_id_mappings(self, pairs: list[tuple[str, str]]) -> int:
        """Insert mtgjson_uuid → card_version_id rows into card_external_identifier.

        Accepts (mtgjson_uuid, scryfall_uuid) pairs from AllIdentifiers.json.
        Resolves card_version_id by joining via existing scryfall_id rows, then
        inserts with identifier_name='mtgjson_id'. Idempotent — the PK
        (card_version_id, card_identifier_ref_id) conflict is silently ignored.

        Uses UNNEST over two text arrays to avoid temp-table transaction coupling.
        Returns the number of rows actually inserted (0 on re-run).
        """
        if not pairs:
            return 0
        mtgjson_uuids = [p[0] for p in pairs]
        scryfall_uuids = [p[1] for p in pairs]
        count = await self.connection.fetchval("""
            WITH pairs AS (
                SELECT
                    unnest($1::text[]) AS mtgjson_uuid,
                    unnest($2::text[]) AS scryfall_uuid
            ),
            inserted AS (
                INSERT INTO card_catalog.card_external_identifier
                    (card_identifier_ref_id, card_version_id, value)
                SELECT
                    mtgjson_ref.card_identifier_ref_id,
                    scryfall_cei.card_version_id,
                    p.mtgjson_uuid
                FROM pairs p
                JOIN card_catalog.card_external_identifier scryfall_cei
                    ON scryfall_cei.value = p.scryfall_uuid
                JOIN card_catalog.card_identifier_ref scryfall_ref
                    ON scryfall_ref.card_identifier_ref_id = scryfall_cei.card_identifier_ref_id
                   AND scryfall_ref.identifier_name = 'scryfall_id'
                CROSS JOIN (
                    SELECT card_identifier_ref_id
                    FROM card_catalog.card_identifier_ref
                    WHERE identifier_name = 'mtgjson_id'
                ) mtgjson_ref
                ON CONFLICT (card_version_id, card_identifier_ref_id) DO NOTHING
                RETURNING 1
            )
            SELECT COUNT(*) FROM inserted
        """, mtgjson_uuids, scryfall_uuids)
        return count or 0

    async def upsert_mtgjson_id_mappings(self, pairs: list[tuple[str, str]]) -> int:
        """Insert mtgjson_uuid → card_version_id rows into card_external_identifier.

        Accepts (mtgjson_uuid, scryfall_uuid) pairs from AllIdentifiers.json.
        Resolves card_version_id by joining via existing scryfall_id rows, then
        inserts with identifier_name='mtgjson_id'. Idempotent — the PK
        (card_version_id, card_identifier_ref_id) conflict is silently ignored.

        Uses UNNEST over two text arrays to avoid temp-table/transaction coupling.
        Returns the number of rows actually inserted (0 on a re-run).
        """
        if not pairs:
            return 0
        mtgjson_uuids = [p[0] for p in pairs]
        scryfall_uuids = [p[1] for p in pairs]
        count = await self.connection.fetchval("""
            WITH pairs AS (
                SELECT
                    unnest($1::text[]) AS mtgjson_uuid,
                    unnest($2::text[]) AS scryfall_uuid
            ),
            inserted AS (
                INSERT INTO card_catalog.card_external_identifier
                    (card_identifier_ref_id, card_version_id, value)
                SELECT
                    mtgjson_ref.card_identifier_ref_id,
                    scryfall_cei.card_version_id,
                    p.mtgjson_uuid
                FROM pairs p
                JOIN card_catalog.card_external_identifier scryfall_cei
                    ON scryfall_cei.value = p.scryfall_uuid
                JOIN card_catalog.card_identifier_ref scryfall_ref
                    ON scryfall_ref.card_identifier_ref_id = scryfall_cei.card_identifier_ref_id
                   AND scryfall_ref.identifier_name = 'scryfall_id'
                CROSS JOIN (
                    SELECT card_identifier_ref_id
                    FROM card_catalog.card_identifier_ref
                    WHERE identifier_name = 'mtgjson_id'
                ) mtgjson_ref
                ON CONFLICT (card_version_id, card_identifier_ref_id) DO NOTHING
                RETURNING 1
            )
            SELECT COUNT(*) FROM inserted
        """, mtgjson_uuids, scryfall_uuids)
        return count or 0

    async def promote_staging_to_production(self) -> None:
        """Call the batched promoter proc to move staged rows into price_observation.

        Timeout + transaction semantics are set by the service registration,
        not this method:

        - ``runs_in_transaction=False`` on the service gives the connection
          a non-atomic context so the proc's internal ``COMMIT``/``ROLLBACK``
          per batch is legal.
        - ``command_timeout=<seconds>`` on the service swaps the connection's
          ``_config`` namedtuple in ``ServiceManager._execute_service`` so
          asyncpg's ``_get_timeout_impl`` fallback lifts to our override
          instead of the 60 s pool default, and also applies a matching
          server-side ``statement_timeout`` GUC.

        From this method's point of view it's a bare ``CALL`` on whatever
        connection it was handed.
        """
        await self.execute_command(
            "CALL pricing.load_price_observation_from_mtgjson_staging_batched()",
            (),
        )

    # ------------------------------------------------------------------ #
    # AbstractRepository contract                                         #
    # ------------------------------------------------------------------ #
    #
    # There is no MTGJson-owned CRUD entity in this repo anymore: the raw
    # payload table was dropped in migration 15 and the streamer writes
    # directly into `pricing.mtgjson_card_prices_staging`. The abstract
    # methods therefore have nothing to bind to and raise NotImplementedError
    # rather than masquerading as half-usable shims.

    async def add(self, item: Any) -> None:
        raise NotImplementedError(
            "MtgjsonRepository is ingest-only via `copy_staging_batch`. "
            "There is no domain entity to `add`."
        )

    async def get(self, id: Any) -> None:
        raise NotImplementedError(
            "MtgjsonRepository is ingest-only; staged rows are consumed by "
            "`load_price_observation_from_mtgjson_staging_batched` and deleted."
        )

    async def list(self, *_: Any, **__: Any) -> list:
        raise NotImplementedError(
            "MtgjsonRepository is ingest-only; query `pricing.price_observation` "
            "for the promoted, canonical price history."
        )

    async def update(self, item: Any) -> None:
        raise NotImplementedError(
            "MtgjsonRepository writes are append-only via `copy_staging_batch`."
        )

    async def delete(self, id: Any) -> None:
        raise NotImplementedError(
            "MtgjsonRepository writes are append-only; promoted rows are "
            "cleaned up by the promoter proc itself."
        )
