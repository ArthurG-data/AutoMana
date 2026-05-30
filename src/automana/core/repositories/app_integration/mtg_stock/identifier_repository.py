import logging
from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository

logger = logging.getLogger(__name__)


class MtgstockIdentifierRepository(AbstractRepository):

    def __init__(self, connection, executor=None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "MtgstockIdentifierRepository"

    async def get_mtgstock_ref_id(self) -> int:
        return await self.execute_fetchval(
            "SELECT card_identifier_ref_id FROM card_catalog.card_identifier_ref "
            "WHERE identifier_name = 'mtgstock_id'"
        )

    async def get_existing_mapped_print_ids(self) -> set[int]:
        ref_id = await self.get_mtgstock_ref_id()
        rows = await self.execute_query(
            "SELECT value::int FROM card_catalog.card_external_identifier "
            "WHERE card_identifier_ref_id = $1",
            (ref_id,),
        )
        return {r["value"] for r in rows}

    async def fetch_by_scryfall(self, scryfall_ids: list[str]) -> dict[str, str]:
        """Return {scryfall_id: card_version_id} for matching IDs."""
        if not scryfall_ids:
            return {}
        rows = await self.execute_query(
            """
            SELECT cei.value AS scryfall_id, cei.card_version_id::text
            FROM card_catalog.card_external_identifier cei
            JOIN card_catalog.card_identifier_ref cir
              ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
            WHERE cir.identifier_name = 'scryfall_id'
              AND cei.value = ANY($1)
            """,
            (scryfall_ids,),
        )
        return {r["scryfall_id"]: r["card_version_id"] for r in rows}

    async def fetch_by_tcgplayer(self, tcg_ids: list[str]) -> dict[str, str]:
        """Return {tcgplayer_id: card_version_id} for matching IDs."""
        if not tcg_ids:
            return {}
        rows = await self.execute_query(
            """
            SELECT cei.value AS tcg_id, cei.card_version_id::text
            FROM card_catalog.card_external_identifier cei
            JOIN card_catalog.card_identifier_ref cir
              ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
            WHERE cir.identifier_name = 'tcgplayer_id'
              AND cei.value = ANY($1)
            """,
            (tcg_ids,),
        )
        return {r["tcg_id"]: r["card_version_id"] for r in rows}

    async def fetch_by_set_collector(
        self, pairs: list[tuple[str, str]]
    ) -> dict[tuple[str, str], str]:
        """Return {(set_abbr, collector_number): card_version_id} for matching pairs."""
        if not pairs:
            return {}
        set_abbrs = list({p[0].lower() for p in pairs})
        rows = await self.execute_query(
            """
            SELECT lower(s.set_code) AS set_code, cv.collector_number::text, cv.card_version_id::text
            FROM card_catalog.card_version cv
            JOIN card_catalog.sets s ON s.set_id = cv.set_id
            WHERE lower(s.set_code) = ANY($1)
            """,
            (set_abbrs,),
        )
        lookup = {
            (r["set_code"], r["collector_number"]): r["card_version_id"] for r in rows
        }
        return {
            (abbr, num): lookup[(abbr.lower(), str(num))]
            for abbr, num in pairs
            if (abbr.lower(), str(num)) in lookup
        }

    async def upsert_mtgstock_id_mappings(self, mappings: list[dict]) -> int:
        """Insert {card_version_id, print_id} rows. ON CONFLICT DO NOTHING. Returns count."""
        if not mappings:
            return 0
        ref_id = await self.get_mtgstock_ref_id()
        rows = [(m["card_version_id"], ref_id, str(m["print_id"])) for m in mappings]
        await self.execute_many(
            """
            INSERT INTO card_catalog.card_external_identifier
                (card_version_id, card_identifier_ref_id, value)
            VALUES ($1, $2, $3)
            ON CONFLICT DO NOTHING
            """,
            rows,
        )
        return len(rows)

    def add(self, item=None):
        raise NotImplementedError("Method not implemented")

    def delete(self, id=None):
        raise NotImplementedError("Method not implemented")

    def get(self, id=None):
        raise NotImplementedError("Method not implemented")

    def update(self, item=None):
        raise NotImplementedError("Method not implemented")

    async def list(self, items=None):
        raise NotImplementedError("Method not implemented")
