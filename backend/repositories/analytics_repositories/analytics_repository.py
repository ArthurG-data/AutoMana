from backend.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository

class AnalyticsRepository(AbstractRepository):

    @property
    def name(self) -> str:
        return "AnalyticsRepository"
    
    async def generate_daily_summary_report(self) -> dict:
        query = """
        SELECT
            (SELECT COUNT(*) FROM card_catalog.sets WHERE created_at >= NOW() - INTERVAL '1 day') AS new_sets,
            (SELECT COUNT(*) FROM card_catalog.card_version WHERE created_at >= NOW() - INTERVAL '1 day') AS new_cards,
            (SELECT COUNT(*) FROM card_catalog.card_version) AS total_cards,
            (SELECT COUNT(*) FROM card_catalog.sets) AS total_sets,
            (SELECT COALESCE(json_agg(row_to_json(s)), '[]'::json) FROM card_catalog.sets s WHERE s.created_at >= NOW() - INTERVAL '1 day') AS new_sets_added,
            (SELECT COALESCE(json_agg(row_to_json(c)), '[]'::json) FROM card_catalog.card_version c WHERE c.created_at >= NOW() - INTERVAL '1 day') AS new_cards_added,
            (SELECT COALESCE(json_agg(json_build_object('pipeline_name', pipeline_name, 'status', status)), '[]'::json) FROM ops.ingestion_runs WHERE created_at >= NOW() - INTERVAL '1 day') AS ingestion_runs
        """
        result = await self.execute_query(query)
        if result and len(result) > 0:
            return {
                "new_sets_count": result[0].get("new_sets", 0),
                "new_cards_count": result[0].get("new_cards", 0),
                "total_cards_count": result[0].get("total_cards", 0),
                "total_sets_count": result[0].get("total_sets", 0),
                "new_sets_added": result[0].get("new_sets_added", []),
                "new_cards_added": result[0].get("new_cards_added", []),
                "ingestion_runs": result[0].get("ingestion_runs", []),
            }
        return {"new_sets_count": 0, "new_cards_count": 0}
    
    async def add(self, data: dict) -> None:
        pass
    async def update(self, id: int, data: dict) -> None:
        pass
    async def delete(self, id: int) -> None:
        pass
    async def get(self, id: int) -> dict | None:
        pass
    async def list(self, filters: dict | None = None) -> list[dict]:
        pass