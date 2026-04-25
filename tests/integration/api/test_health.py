"""
Phase 0 smoke test: the whole rig works.

If this passes, the following are proven end-to-end:
  1. testcontainers-python starts Timescale + Redis images.
  2. Env override fixture primes the Settings cache with container host/port.
  3. Migration runner applies all SQL files cleanly against a fresh DB.
  4. FastAPI lifespan fires without errors (init_async_pool connects to the
     test container successfully).
  5. ASGITransport + httpx 0.28 plumbing is correctly wired.

It does not touch auth, DB data, or any domain logic — that is what later
phases cover. This test exists solely as the canary for the scaffolding.
"""
import pytest


pytestmark = [pytest.mark.integration, pytest.mark.api]


async def test_health_endpoint_returns_200(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
