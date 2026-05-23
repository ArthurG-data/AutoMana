"""DB repository for daily FX rates."""
from __future__ import annotations

import logging
from datetime import date

from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository

logger = logging.getLogger(__name__)

_UPSERT_RATE = """
INSERT INTO pricing.fx_rates (rate_date, from_currency, to_currency, rate)
VALUES ($1, $2, $3, $4)
ON CONFLICT (rate_date, from_currency, to_currency) DO UPDATE
    SET rate = EXCLUDED.rate, fetched_at = now();
"""

_GET_RATES_FOR_DATE = """
SELECT from_currency, rate
FROM pricing.fx_rates
WHERE to_currency = 'USD'
  AND rate_date = $1
ORDER BY from_currency;
"""


class FxRatesRepository(AbstractRepository):
    def __init__(self, connection, executor=None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "FxRatesRepository"

    async def add(self, item=None) -> None:
        pass

    async def get(self, id=None):
        return None

    async def update(self, item=None) -> None:
        pass

    async def delete(self, id=None) -> None:
        pass

    async def list(self, items=None) -> list:
        return []

    async def upsert_rate(
        self,
        rate_date: date,
        from_currency: str,
        to_currency: str,
        rate: float,
    ) -> None:
        await self.execute_command(_UPSERT_RATE, (rate_date, from_currency, to_currency, rate))

    async def get_rates_for_date(self, rate_date: date) -> list[dict]:
        rows = await self.execute_query(_GET_RATES_FOR_DATE, (rate_date,))
        return [dict(r) for r in rows] if rows else []
