from datetime import datetime
from typing import  Optional, Any, Sequence
from uuid import UUID
from dataclasses import dataclass, field

from backend.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository
from backend.repositories.card_catalog import card_queries as queries 

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

    async def add_many(self, values):
        #not async anymore
        result = await self.execute_query("SELECT * FROM card_catalog.insert_batch_card_versions($1::JSONB)", (values,))
        batch_result = result[0] if result else {}
        response = CardReferenceRepository.BatchInsertResponse(
            total_processed=batch_result.get('total_processed', 0),
            successful_inserts=batch_result.get('successful_inserts', 0),
            failed_inserts=batch_result.get('failed_inserts', 0),
            inserted_card_ids=batch_result.get('inserted_card_ids', []),
            errors=batch_result.get('error_details', [])
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