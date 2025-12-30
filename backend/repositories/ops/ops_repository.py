import json
from backend.repositories.AbstractRepository import AbstractRepository
from backend.repositories.ops.scryfall_data import update_bulk_scryfall_data_sql, test as test_sql


class OpsRepository(AbstractRepository):

    @property
    def name(self):
        return "OpsRepository"
    

    async def start_pipeline(self):
        query = """
        INSERT INTO ops.ingestion_runs (pipeline_name, status)
        VALUES ('scryfall_data_pipeline', 'started')
        RETURNING id
        """
        result =await self.execute_query(query)
        return result[0].get("id") if result and len(result) > 0 else None

    async def get_bulk_data_uri(self):
        query = """
        SELECT r.api_uri AS uri, r.source_id AS source_id
        FROM ops.resources r
        JOIN ops.sources s ON s.kind = 'http' and s.name = 'scryfall' AND r.external_type = 'bulk_data'
        ORDER BY s.updated_at DESC
        LIMIT 1;
        """
        result = await self.execute_query(query)
        return result[0].get("uri") if result and len(result) > 0 else None
    

    async def update_bulk_data_uri_return_new(self, items: dict, source_id: int):
        result = await self.execute_query(
            #update_bulk_scryfall_data_sql,
            update_bulk_scryfall_data_sql,
            (json.dumps(items), source_id)#source_id
        )
        print(result)
        record = result[0] if result and len(result) > 0 else None
        ressources_upserted = record.get("resources_upserted") if record else 0
        versions_inserted = record.get("versions_inserted") if record else 0
        changed_items = record.get("changed") if record else []
        return {
        "source_id": source_id,
        "resources_upserted": ressources_upserted,
        "versions_inserted": versions_inserted,
        "changed": changed_items
    }
    async def get():
        raise NotImplementedError("This method is not implemented yet.")
    
    async def add():
        raise NotImplementedError("This method is not implemented yet.")
    async def update():
        raise NotImplementedError("This method is not implemented yet.")
    async def delete():
        raise NotImplementedError("This method is not implemented yet.")
    async def list():
        raise NotImplementedError("This method is not implemented yet.")