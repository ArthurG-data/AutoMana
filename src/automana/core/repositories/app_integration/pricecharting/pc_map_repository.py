"""Repository for pricing.pricecharting_card_map — the persistent PC product ->
card_version match cache + provenance."""
from __future__ import annotations

import logging

from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository

logger = logging.getLogger(__name__)

_FETCH_ALL_SQL = """
SELECT pc_product_id, card_version_id, set_code, finish_id,
       match_method, certainty, tcg_vote_count, verified
FROM   pricing.pricecharting_card_map
"""

_FETCH_MATCHED_SQL = """
SELECT pc_product_id, card_version_id, finish_id
FROM   pricing.pricecharting_card_map
WHERE  card_version_id IS NOT NULL
"""

# Bulk upsert. A `verified` row is a manual lock — the WHERE on DO UPDATE leaves
# it untouched. card_version_id NULL is a recorded miss, not a skip-cache.
_UPSERT_SQL = """
INSERT INTO pricing.pricecharting_card_map AS t
    (pc_product_id, card_version_id, set_code, finish_id,
     match_method, certainty, tcg_vote_count, updated_at)
SELECT u.pc, u.cv, u.sc, u.fi, u.mm, u.ce, u.tv, now()
FROM   unnest($1::text[], $2::uuid[], $3::text[], $4::smallint[],
              $5::text[], $6::smallint[], $7::smallint[])
       AS u(pc, cv, sc, fi, mm, ce, tv)
ON CONFLICT (pc_product_id) DO UPDATE SET
    card_version_id = EXCLUDED.card_version_id,
    set_code        = EXCLUDED.set_code,
    finish_id       = EXCLUDED.finish_id,
    match_method    = EXCLUDED.match_method,
    certainty       = EXCLUDED.certainty,
    tcg_vote_count  = EXCLUDED.tcg_vote_count,
    updated_at      = now()
WHERE  t.verified = false
"""


class PricechartingMapRepository(AbstractRepository):
    @property
    def name(self) -> str:
        return "pricecharting_card_map"

    async def fetch_all_map(self) -> dict[str, dict]:
        """Every mapped product -> its full row (keyed by pc_product_id).

        Used by the matching service to decide which products to skip
        (already resolved or verified) vs re-attempt.
        """
        rows = await self.execute_query(_FETCH_ALL_SQL)
        return {r["pc_product_id"]: dict(r) for r in rows}

    async def fetch_matched_map(self) -> dict[str, dict]:
        """Resolved products only -> {card_version_id, finish_id}. Used by staging."""
        rows = await self.execute_query(_FETCH_MATCHED_SQL)
        return {
            r["pc_product_id"]: {
                "card_version_id": str(r["card_version_id"]),
                "finish_id": r["finish_id"],
            }
            for r in rows
        }

    async def upsert_map(self, rows: list[dict]) -> int:
        """Bulk upsert match rows. Never overwrites a `verified` row. Returns the
        number of rows submitted."""
        if not rows:
            return 0
        await self.execute_command(_UPSERT_SQL, (
            [r["pc_product_id"] for r in rows],
            [r.get("card_version_id") for r in rows],
            [r.get("set_code") for r in rows],
            [r.get("finish_id") for r in rows],
            [r.get("match_method", "none") for r in rows],
            [int(r.get("certainty", 0)) for r in rows],
            [int(r.get("tcg_vote_count", 0)) for r in rows],
        ))
        return len(rows)

    # AbstractRepository abstract stubs (not used for this command/query repo).
    async def add(self, item):  # pragma: no cover
        raise NotImplementedError

    async def get(self, id):  # pragma: no cover
        raise NotImplementedError

    async def update(self, item):  # pragma: no cover
        raise NotImplementedError

    async def delete(self, id):  # pragma: no cover
        raise NotImplementedError

    async def list(self, *_, **__):  # pragma: no cover
        raise NotImplementedError
