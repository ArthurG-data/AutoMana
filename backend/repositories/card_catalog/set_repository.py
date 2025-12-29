from dataclasses import dataclass, field
from backend.repositories.AbstractRepository import AbstractRepository
from typing import Any, Optional, Sequence
from uuid import UUID
from backend.schemas.card_catalog.set import NewSet
import logging

logger = logging.getLogger(__name__)

class SetReferenceRepository(AbstractRepository[Any]):
    def __init__(self, connection, executor=None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "SetReferenceRepository"

    async def add(self
                  , id: UUID
                  , set_name: str
                  , set_code: str
                  , set_type: str
                  , released_at: str
                  , digital: bool
                  , nonfoil_only: bool = False
                  , foil_only: bool = False
                  , parent_set: Optional[str] = None) -> dict:
        query = "SELECT insert_joined_set ($1, $2, $3, $4, $5, $6, $7, $8, $9)"
        values = (id, set_name, set_code, set_type, released_at, digital, nonfoil_only, foil_only, parent_set)
        return await self.execute_command(query, values)
        
    @dataclass(slots=True)
    class BatchInsertResponse:
        total_processed: int
        successful_inserts: int
        failed_inserts: int
        success_rate: float = field(init=False)
        inserted_set_ids: list[UUID]
        errors: list[str]

        def __post_init__(self)->None:
            self.success_rate = (
                self.successful_inserts / self.total_processed * 100
                if self.total_processed > 0
                else 0
            )

    async def add_many(self, values) -> BatchInsertResponse:
        """not async anymaore because using a transaction block"""
        query =  "SELECT * FROM card_catalog.insert_batch_sets($1::JSONB);"

        result = await self.execute_query(query, (values,))
        batch_result = result[0] if result else {}
        response = SetReferenceRepository.BatchInsertResponse(
            total_processed=batch_result.get('total_processed', 0),
            successful_inserts=batch_result.get('successful_inserts', 0),
            failed_inserts=batch_result.get('failed_inserts', 0),
            inserted_set_ids=batch_result.get('inserted_set_ids', []),
            errors=batch_result.get('error_details', [])
        )
        return response

       
    async def delete(self, set_id: UUID):
        query = """
        UPDATE card_catalog.sets 
        SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP 
        WHERE set_id = $1 AND is_active = TRUE
        RETURNING set_id
    """
        values = (set_id,)
        result = await self.execute_command(query, values)
        return bool(result)

    async def update(self, set_id: UUID, **kwargs):
        updates = {k: v for k, v in kwargs.items() if v is not None}
        if not updates:
            return {"message": "No fields to update"}
        
        # Start building query components
        update_parts = []
        cte_parts = []
        params = []
        counter = 1
        
        # Handle special fields that need CTE handling
        needs_cte = False
        
        # Handle set_type if present
        if 'set_type' in updates:
            needs_cte = True
            cte_parts.append(f"""
                ins_set_type AS (
                    INSERT INTO card_catalog.set_type_list_ref (set_type)
                    VALUES (${counter})
                    ON CONFLICT DO NOTHING
                    RETURNING set_type_id
                ),
                get_set_type AS (
                    SELECT set_type_id FROM ins_set_type
                    UNION
                    SELECT set_type_id FROM card_catalog.set_type_list_ref WHERE set_type = ${counter}
                )""")
            params.append(updates['set_type'])
            update_parts.append("set_type_id = (SELECT set_type_id FROM get_set_type)")
            counter += 1
            # Remove from regular updates as it's handled specially
            del updates['set_type']
        
        # Handle foil_status if present
        if 'foil_status_id' in updates:
            needs_cte = True
            cte_parts.append(f"""
                ins_foil_ref AS (
                    INSERT INTO card_catalog.foil_status_ref (foil_status_desc)
                    VALUES (${counter})
                    ON CONFLICT DO NOTHING
                    RETURNING foil_status_id
                ),
                get_foil_ref AS (
                    SELECT foil_status_id FROM ins_foil_ref
                    UNION
                    SELECT foil_status_id FROM card_catalog.foil_status_ref WHERE foil_status_desc = ${counter}
                )""")
            params.append(updates['foil_status_id'])
            update_parts.append("foil_status_id = (SELECT foil_status_id FROM get_foil_ref)")
            counter += 1
            del updates['foil_status_id']
        
        # Handle parent_set if present
        if 'parent_set' in updates:
            needs_cte = True
            cte_parts.append(f"""
                get_parent_set AS (
                    SELECT set_id from card_catalog.sets
                    WHERE set_name = ${counter}
                )""")
            params.append(updates['parent_set'])
            update_parts.append("parent_set_id = (SELECT set_id FROM get_parent_set)")
            counter += 1
            del updates['parent_set']
        
        # Add all other fields
        for field, value in updates.items():
            update_parts.append(f"{field} = ${counter}")
            params.append(value)
            counter += 1
        
        # Build the final query
        query_parts = []
        
        # Add CTE if needed
        if needs_cte:
            query_parts.append("WITH")
            query_parts.append(",\n".join(cte_parts))
        
        # Add UPDATE statement
        query_parts.append(f"UPDATE sets SET {', '.join(update_parts)}")
        
        # Add WHERE clause with set_id
        query_parts.append(f"WHERE set_id = ${counter}")
        params.append(set_id)
        
        # Add RETURNING clause
        query_parts.append("RETURNING *")
        
        # Join all query parts
        query = " ".join(query_parts)
        
        try:
            # Execute the query
            result = await self.execute_query(query, tuple(params))
            return result
        except Exception as e:
            logger.error(f"Error updating set {set_id}: {str(e)}")
            raise

    async def get(self, set_id: UUID) -> dict[str, Any]|None:
        query = """ 
                SELECT * FROM card_catalog.joined_set_materialized WHERE set_id = $1
        """
        result =  await self.execute_query(query, set_id)
        return result[0] if result else None
    
    async def list(self, limit: int = 100, offset: int = 0, ids: Optional[Sequence[UUID]] = None):
        query = "SELECT * FROM card_catalog.joined_set_materialized"
        counter = 1
        values = []
        if ids:
            query += f" WHERE set_id = ANY(${counter})"
            counter +=1
            values.append(list(ids))
        query += f" LIMIT ${counter} OFFSET ${counter + 1}"
        values.extend([limit, offset])
        logger.debug(f"Executing query: {query} with values: {values}")
        return await self.execute_query(query, tuple(values))