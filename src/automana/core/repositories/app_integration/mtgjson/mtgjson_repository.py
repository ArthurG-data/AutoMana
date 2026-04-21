import json
from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository


class MtgjsonRepository(AbstractRepository):

    @property
    def name(self) -> str:
        return "MtgjsonRepository"

    async def insert_payload(self, source: str, filename: str, payload: dict) -> str:
        rows = await self.execute_query(
            "INSERT INTO pricing.mtgjson_payloads (source, filename, payload)"
            " VALUES ($1, $2, $3::jsonb) RETURNING id",
            source, filename, json.dumps(payload)
        )
        return str(rows[0]["id"])

    async def call_process_payload(self, payload_id: str) -> None:
        await self.execute_command(
            "CALL pricing.process_mtgjson_payload($1::uuid)", payload_id
        )

    async def promote_staging_to_production(self, payload_id: str) -> None:
        await self.execute_command("CALL pricing.load_price_observation_from_mtgjson_staging_batched($1::uuid)", payload_id)