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
