import pytest
from datetime import date
from unittest.mock import AsyncMock, patch

from automana.core.services.pricing.fetch_fx_rates_service import fetch_fx_rates


@pytest.mark.asyncio
async def test_fetch_fx_rates_upserts_aud_and_cad():
    mock_repo = AsyncMock()
    fake_api_response = {"base": "USD", "date": "2026-05-22", "rates": {"AUD": 1.58, "CAD": 1.36}}

    with patch(
        "automana.core.services.pricing.fetch_fx_rates_service._fetch_rates_from_api",
        new_callable=AsyncMock,
        return_value=fake_api_response,
    ):
        result = await fetch_fx_rates(fx_rates_repository=mock_repo)

    assert mock_repo.upsert_rate.call_count == 2
    calls = {c.kwargs["from_currency"]: c.kwargs for c in mock_repo.upsert_rate.call_args_list}
    assert "AUD" in calls
    assert "CAD" in calls
    assert abs(calls["AUD"]["rate"] - (1 / 1.58)) < 0.0001
    assert abs(calls["CAD"]["rate"] - (1 / 1.36)) < 0.0001
    assert calls["AUD"]["to_currency"] == "USD"
    assert result["rates_upserted"] == 2


@pytest.mark.asyncio
async def test_fetch_fx_rates_handles_api_failure_gracefully():
    mock_repo = AsyncMock()

    with patch(
        "automana.core.services.pricing.fetch_fx_rates_service._fetch_rates_from_api",
        new_callable=AsyncMock,
        side_effect=Exception("network error"),
    ):
        result = await fetch_fx_rates(fx_rates_repository=mock_repo)

    mock_repo.upsert_rate.assert_not_called()
    assert result["rates_upserted"] == 0
