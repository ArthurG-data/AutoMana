import logging
from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository

logger = logging.getLogger(__name__)

# Shared CTE: one row per mapped print_id with its set release date and the
# latest MTGStocks TCG list-average (the tiering signal).
_TIER_CTE = """
WITH tiered AS (
  SELECT cei.value::int AS print_id, s.released_at,
         MAX(ppl.list_avg_cents) AS list_avg_cents
  FROM card_catalog.card_external_identifier cei
  JOIN card_catalog.card_identifier_ref cir
    ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
  JOIN card_catalog.card_version cv ON cv.card_version_id = cei.card_version_id
  JOIN card_catalog.sets s ON s.set_id = cv.set_id
  LEFT JOIN pricing.print_price_latest ppl
    ON ppl.card_version_id = cv.card_version_id
   AND ppl.source_id = (SELECT source_id FROM pricing.price_source WHERE code = 'mtgstocks')
  WHERE cir.identifier_name = 'mtgstock_id'
  GROUP BY cei.value, s.released_at
)
"""

# Each predicate is the complement of the higher tiers, so every mapped
# print_id falls into exactly one tier. COALESCE treats a null price as 0,
# so null-price cards that are not recent sets land in tier 3 (without
# COALESCE, `NOT (NULL >= 100)` is NULL and the row would fall through all tiers).
_TIER1 = "(released_at >= CURRENT_DATE - INTERVAL '120 days' OR COALESCE(list_avg_cents, 0) >= 500)"
_TIER2 = f"NOT {_TIER1} AND COALESCE(list_avg_cents, 0) >= 100"
_TIER3 = f"NOT {_TIER1} AND COALESCE(list_avg_cents, 0) < 100"

_TIER_PREDICATE = {1: _TIER1, 2: _TIER2, 3: _TIER3}


class MtgstockPriorityRepository(AbstractRepository):

    def __init__(self, connection, executor=None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "MtgstockPriorityRepository"

    async def fetch_tier_print_ids(self, tier: int) -> list[int]:
        """Return the sorted print_ids belonging to the given tier (1, 2, or 3)."""
        predicate = _TIER_PREDICATE.get(tier)
        if predicate is None:
            raise ValueError(f"Unknown tier: {tier}")
        query = (
            _TIER_CTE
            + f"SELECT print_id FROM tiered WHERE {predicate} ORDER BY print_id"
        )
        rows = await self.execute_query(query)
        return sorted(r["print_id"] for r in rows)

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
