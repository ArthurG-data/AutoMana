"""Nightly FX rate fetch — AUD→USD and CAD→USD from frankfurter.app."""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

import httpx

from automana.core.repositories.pricing.fx_rates_repository import FxRatesRepository
from automana.core.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)

_FRANKFURTER_URL = "https://api.frankfurter.app/latest"
_TARGET_CURRENCIES = ("AUD", "CAD")


async def _fetch_rates_from_api() -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            _FRANKFURTER_URL,
            params={"from": "USD", "to": ",".join(_TARGET_CURRENCIES)},
        )
        resp.raise_for_status()
        return resp.json()


@ServiceRegistry.register(
    path="integrations.pricing.fetch_fx_rates",
    db_repositories=["fx_rates"],
    runs_in_transaction=False,
)
async def fetch_fx_rates(
    fx_rates_repository: FxRatesRepository,
    **kwargs: Any,
) -> dict:
    """Fetch daily USD→AUD and USD→CAD rates; store inverse (AUD→USD, CAD→USD)."""
    try:
        data = await _fetch_rates_from_api()
    except Exception:
        logger.exception("fetch_fx_rates_api_failed")
        return {"rates_upserted": 0}

    today = date.today()
    upserted = 0
    rates: dict = data.get("rates", {})

    for currency, usd_per_foreign in rates.items():
        if currency not in _TARGET_CURRENCIES:
            continue
        try:
            await fx_rates_repository.upsert_rate(
                rate_date=today,
                from_currency=currency,
                to_currency="USD",
                rate=1.0 / usd_per_foreign,   # AUD→USD = inverse of USD→AUD
            )
            upserted += 1
        except Exception:
            logger.exception("fetch_fx_rates_upsert_failed", extra={"currency": currency})

    logger.info("fetch_fx_rates_complete", extra={"rates_upserted": upserted})
    return {"rates_upserted": upserted}
