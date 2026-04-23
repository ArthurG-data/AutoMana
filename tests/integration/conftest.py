"""
Integration-test scaffolding.

Responsibilities:
- Start session-scoped TimescaleDB (with pgvector) and Redis containers.
- Point automana Settings at the containers via env vars BEFORE any automana
  module is imported, and clear the lru_cache on get_settings.
- Apply SQL schema/migrations against the fresh container.
- Provide an async httpx client with the full FastAPI lifespan running.

Why env vars are set in a fixture and not at module level:
get_settings reads env vars at import time (main.py calls it at line 81).
Containers assign random host ports, so we can only set the correct values
AFTER the container starts. Every fixture that touches automana code must
depend on _test_env so the env is primed first, and no test module imports
automana at the top level — imports are deferred inside fixtures.
"""
from __future__ import annotations

import os
import pathlib

import pytest
import pytest_asyncio


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
EXTENSIONS_SQL = PROJECT_ROOT / "infra" / "db" / "init" / "00-extensions.sql"
SCHEMAS_DIR = PROJECT_ROOT / "src" / "automana" / "database" / "SQL" / "schemas"
ANALYTICS_DIR = PROJECT_ROOT / "src" / "automana" / "database" / "SQL" / "analytics"
MIGRATIONS_DIR = PROJECT_ROOT / "infra" / "db" / "init" / "migrations"


# -----------------------------------------------------------------------------
# Containers
# -----------------------------------------------------------------------------
TIMESCALE_IMAGE = os.environ.get("AUTOMANA_TEST_TIMESCALE_IMAGE", "timescale-pgvector:pg17")
REDIS_IMAGE = os.environ.get("AUTOMANA_TEST_REDIS_IMAGE", "redis:7-alpine")


@pytest.fixture(scope="session")
def timescale_container():
    """TimescaleDB + pgvector. Defaults to the local dev image built by
    deploy/docker/postgres/Dockerfile (`timescale-pgvector:pg17`, ~258MB).
    CI can override with AUTOMANA_TEST_TIMESCALE_IMAGE=timescale/timescaledb-ha:pg17-all."""
    from testcontainers.postgres import PostgresContainer

    container = PostgresContainer(
        image=TIMESCALE_IMAGE,
        username="automana_test",
        password="test_password",
        dbname="automana_test",
    )
    with container:
        yield container


@pytest.fixture(scope="session")
def redis_container():
    from testcontainers.redis import RedisContainer

    with RedisContainer(image=REDIS_IMAGE) as container:
        yield container


# -----------------------------------------------------------------------------
# Env override (must run before automana.api.main is imported)
# -----------------------------------------------------------------------------
@pytest.fixture(scope="session")
def _test_env(timescale_container, redis_container):
    db_host = timescale_container.get_container_host_ip()
    db_port = str(timescale_container.get_exposed_port(5432))
    redis_host = redis_container.get_container_host_ip()
    redis_port = str(redis_container.get_exposed_port(6379))

    overrides = {
        "ENV": "test",
        "POSTGRES_HOST": db_host,
        "POSTGRES_PORT": db_port,
        "DB_NAME": "automana_test",
        "APP_BACKEND_DB_USER": "automana_test",
        "POSTGRES_USER": "automana_test",
        "POSTGRES_PASSWORD": "test_password",
        "JWT_SECRET_KEY": "test-jwt-secret-do-not-use-in-prod",
        "PGP_SECRET_KEY": "test-pgp-secret-do-not-use-in-prod",
        "DATA_DIR": "/tmp/automana_test_data",
        "REDIS_HOST": redis_host,
        "REDIS_PORT": redis_port,
    }
    previous = {k: os.environ.get(k) for k in overrides}
    os.environ.update(overrides)

    # If anything already imported get_settings (e.g. during test collection),
    # nuke the cache so the next call reads our overrides.
    from automana.core.settings import get_settings

    get_settings.cache_clear()

    yield

    get_settings.cache_clear()
    for k, old in previous.items():
        if old is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = old


# -----------------------------------------------------------------------------
# Migration runner (sync psycopg2 — avoids session-scoped async loop headaches)
# -----------------------------------------------------------------------------
def _collect_sql_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    if EXTENSIONS_SQL.exists():
        files.append(EXTENSIONS_SQL)
    files.extend(sorted(SCHEMAS_DIR.glob("[0-9]*_*.sql")))
    integrity = SCHEMAS_DIR / "integrity_checks.sql"
    if integrity.exists():
        files.append(integrity)
    files.extend(sorted(ANALYTICS_DIR.glob("*.sql")))
    files.extend(sorted(MIGRATIONS_DIR.glob("*.sql")))
    return files


@pytest.fixture(scope="session")
def db_migrations_applied(timescale_container, _test_env):
    import psycopg2

    host = timescale_container.get_container_host_ip()
    port = timescale_container.get_exposed_port(5432)
    conn = psycopg2.connect(
        host=host,
        port=port,
        user="automana_test",
        password="test_password",
        dbname="automana_test",
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for sql_file in _collect_sql_files():
                body = sql_file.read_text().strip()
                if not body:
                    continue
                try:
                    cur.execute(body)
                except Exception as exc:
                    raise RuntimeError(f"Migration failed: {sql_file} -> {exc}") from exc
    finally:
        conn.close()
    yield


# -----------------------------------------------------------------------------
# FastAPI app with lifespan
# -----------------------------------------------------------------------------
@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def test_app(db_migrations_applied):
    from asgi_lifespan import LifespanManager
    # Deferred import — env must be primed first.
    from automana.api.main import app

    async with LifespanManager(app):
        yield app


@pytest_asyncio.fixture(loop_scope="session")
async def client(test_app):
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
