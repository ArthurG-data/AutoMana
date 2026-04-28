from typing import Optional, List
from uuid import UUID
from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository
from automana.core.models.collections.collection import CreateCollection
from automana.api.schemas.user_management.user import UserInDB

class CollectionRepository(AbstractRepository):
    def __init__(self, connection, executor = None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "CollectionRepository"
    
    async def get(self, collection_id: UUID, user_id: UUID) -> Optional[dict]:
        query = """ SELECT c.collection_id, u.username, c.description, c.collection_name,
                           c.created_at, c.is_active
                    FROM user_collection.collections c JOIN user_management.users u
                    ON c.user_id = u.unique_id
                    WHERE c.user_id = $1
                    AND c.is_active = True
                    AND c.collection_id = $2;"""
        result = await self.execute_query(query, (user_id, collection_id))
        return result[0] if result else None

    async def add(self
                  , collection_name:str
                  , description: str
                  , user_id: UUID) -> Optional[dict]:
        query = "INSERT INTO user_collection.collections (collection_name, description, user_id) VALUES ($1, $2, $3) RETURNING collection_id, collection_name, description, user_id, created_at, is_active;"
        result = await self.execute_query(query, (collection_name, description, user_id))
        return result[0] if result else None

    async def add_many(self, values: List[CreateCollection]):
        query = "INSERT INTO user_collection.collections (collection_name, description, user_id) VALUES ($1, $2, $3)  RETURNING collection_id"
        return await self.execute_command(query, (values.collection_name, values.description,    values.user_id))

    async def get_all(self, user_id: UUID) -> List[dict]:
        query = """ SELECT c.collection_id, c.user_id, u.username, c.collection_name,
                           c.description, c.created_at, c.is_active
                    FROM user_collection.collections c JOIN user_management.users u
                    ON c.user_id = u.unique_id
                    WHERE c.user_id = $1 AND c.is_active = True;"""
        return await self.execute_query(query, (user_id,))
    
    async def get_many(self, user_id: UUID, collection_id: List[UUID]):
        placeholders = ', '.join(f'${i + 2}' for i in range(len(collection_id)))
        query = f""" SELECT c.collection_id, c.user_id, u.username, c.collection_name,
                           c.description, c.created_at, c.is_active
                    FROM user_collection.collections c JOIN user_management.users u
                    ON c.user_id = u.unique_id
                    WHERE c.user_id = $1 AND c.is_active = True AND c.collection_id IN ({placeholders});"""
        values = (user_id, *collection_id)
        return await self.execute_query(query, values=values)
   
        
    async def delete(self, collection_id : UUID, user_id : UUID):
        query = "UPDATE user_collection.collections set is_active = False WHERE collection_id = $1 AND user_id = $2;"
        return await self.execute_command(query, (collection_id, user_id))

    async def delete_many(self, collection_ids: List[UUID], user_id: UUID):
        placeholders = ', '.join(f'${i + 2}' for i in range(len(collection_ids)))
        query = f"UPDATE user_collection.collections SET is_active = False WHERE collection_id IN ({placeholders}) AND user_id = $1;"
        return await self.execute_command(query, (user_id, *collection_ids))
    
    async def update(self, update_fields, collection_id, user_id):
        counter = 1
        query = "UPDATE user_collection.collections SET " + ", ".join(f"{k} = ${counter + i}" for i, k in enumerate(update_fields.keys())) + f" WHERE collection_id = ${counter + len(update_fields)} AND user_id =${counter+len(update_fields)+1}"
        values = (*update_fields.values(), collection_id, user_id)
        return await self.execute_command(query, values)

    async def list():
        raise NotImplementedError("This method is not implemented yet")

    # ------------------------------------------------------------------
    # Collection entry methods (all ownership-guarded via collections join)
    # ------------------------------------------------------------------

    async def add_entry(
        self,
        collection_id: UUID,
        user_id: UUID,
        card_version_id: UUID,
        finish_id: int,
        condition: str,
        purchase_price,
        currency_code: str,
        purchase_date,
        language_id,
    ) -> Optional[dict]:
        query = """
            INSERT INTO user_collection.collection_items
                (collection_id, unique_card_id, finish_id, condition,
                 purchase_price, currency_code, purchase_date, language_id)
            SELECT $1, $3, $4, $5, $6, $7, $8, $9
            FROM user_collection.collections
            WHERE collection_id = $1 AND user_id = $2
            RETURNING item_id, collection_id, unique_card_id AS card_version_id,
                      finish_id, condition, purchase_price, currency_code,
                      purchase_date, language_id;
        """
        rows = await self.execute_query(
            query,
            (collection_id, user_id, card_version_id, finish_id, condition,
             purchase_price, currency_code, purchase_date, language_id),
        )
        return dict(rows[0]) if rows else None

    async def get_entry(self, item_id: UUID, collection_id: UUID, user_id: UUID) -> Optional[dict]:
        query = """
            SELECT ci.item_id,
                   ci.collection_id,
                   ci.unique_card_id AS card_version_id,
                   uc.card_name,
                   s.set_code,
                   cv.collector_number,
                   ci.finish_id,
                   cf.code AS finish,
                   ci.condition,
                   ci.purchase_price,
                   ci.currency_code,
                   ci.purchase_date,
                   ci.language_id
            FROM user_collection.collection_items ci
            JOIN user_collection.collections col
                ON col.collection_id = ci.collection_id AND col.user_id = $3
            JOIN card_catalog.card_version cv ON cv.card_version_id = ci.unique_card_id
            JOIN card_catalog.unique_cards_ref uc ON uc.unique_card_id = cv.unique_card_id
            JOIN card_catalog.sets s ON s.set_id = cv.set_id
            JOIN pricing.card_finished cf ON cf.finish_id = ci.finish_id
            WHERE ci.item_id = $1 AND ci.collection_id = $2;
        """
        rows = await self.execute_query(query, (item_id, collection_id, user_id))
        return dict(rows[0]) if rows else None

    async def get_all_entries(self, collection_id: UUID, user_id: UUID) -> List[dict]:
        query = """
            SELECT ci.item_id,
                   ci.collection_id,
                   ci.unique_card_id AS card_version_id,
                   uc.card_name,
                   s.set_code,
                   cv.collector_number,
                   ci.finish_id,
                   cf.code AS finish,
                   ci.condition,
                   ci.purchase_price,
                   ci.currency_code,
                   ci.purchase_date,
                   ci.language_id
            FROM user_collection.collection_items ci
            JOIN user_collection.collections col
                ON col.collection_id = ci.collection_id AND col.user_id = $2
            JOIN card_catalog.card_version cv ON cv.card_version_id = ci.unique_card_id
            JOIN card_catalog.unique_cards_ref uc ON uc.unique_card_id = cv.unique_card_id
            JOIN card_catalog.sets s ON s.set_id = cv.set_id
            JOIN pricing.card_finished cf ON cf.finish_id = ci.finish_id
            WHERE ci.collection_id = $1;
        """
        rows = await self.execute_query(query, (collection_id, user_id))
        return [dict(r) for r in rows]

    async def delete_entry(self, item_id: UUID, collection_id: UUID, user_id: UUID) -> bool:
        query = """
            DELETE FROM user_collection.collection_items ci
            USING user_collection.collections col
            WHERE ci.item_id = $1
              AND ci.collection_id = $2
              AND col.collection_id = ci.collection_id
              AND col.user_id = $3;
        """
        result = await self.execute_command(query, (item_id, collection_id, user_id))
        return result != "DELETE 0"

