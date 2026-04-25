import asyncpg
import pytest_asyncio


@pytest_asyncio.fixture(scope="function")
async def db_pool(timescale_container, _test_env, db_migrations_applied):
    host = timescale_container.get_container_host_ip()
    port = timescale_container.get_exposed_port(5432)
    pool = await asyncpg.create_pool(
        host=host,
        port=int(port),
        user="automana_test",
        password="test_password",
        database="automana_test",
        min_size=1,
        max_size=3,
    )
    yield pool
    await pool.close()
