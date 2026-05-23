import pytest
from unittest.mock import AsyncMock, MagicMock
from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository


class ConcreteRepo(AbstractRepository):
    @property
    def name(self): return "test"
    async def add(self, item): pass
    async def get(self, id): pass
    async def update(self, item): pass
    async def delete(self, id): pass
    async def list(self, items): pass


@pytest.mark.asyncio
async def test_execute_fetchrow_delegates_to_connection():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"id": 1})
    repo = ConcreteRepo(connection=conn)
    result = await repo.execute_fetchrow("SELECT 1", (42,))
    conn.fetchrow.assert_awaited_once_with("SELECT 1", 42)
    assert result == {"id": 1}


@pytest.mark.asyncio
async def test_execute_fetchrow_no_args():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    repo = ConcreteRepo(connection=conn)
    await repo.execute_fetchrow("SELECT now()")
    conn.fetchrow.assert_awaited_once_with("SELECT now()")


@pytest.mark.asyncio
async def test_execute_fetchval_delegates_to_connection():
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=5)
    repo = ConcreteRepo(connection=conn)
    result = await repo.execute_fetchval("SELECT COUNT(*) FROM t", ())
    conn.fetchval.assert_awaited_once_with("SELECT COUNT(*) FROM t")
    assert result == 5


@pytest.mark.asyncio
async def test_execute_copy_to_table_passes_kwargs():
    conn = AsyncMock()
    conn.copy_to_table = AsyncMock(return_value="COPY 10")
    repo = ConcreteRepo(connection=conn)
    buf = MagicMock()
    await repo.execute_copy_to_table("my_table", buf, schema_name="myschema", format="csv")
    conn.copy_to_table.assert_awaited_once_with(
        table_name="my_table", source=buf, schema_name="myschema", format="csv"
    )


@pytest.mark.asyncio
async def test_execute_copy_records_to_table_delegates():
    conn = AsyncMock()
    conn.copy_records_to_table = AsyncMock()
    repo = ConcreteRepo(connection=conn)
    records = [("a", 1), ("b", 2)]
    await repo.execute_copy_records_to_table(
        "my_table", records=records, columns=("col1", "col2"), schema_name="s"
    )
    conn.copy_records_to_table.assert_awaited_once_with(
        "my_table", records=records, columns=("col1", "col2"), schema_name="s"
    )


@pytest.mark.asyncio
async def test_execute_procedure_no_args():
    conn = AsyncMock()
    conn.execute = AsyncMock()
    repo = ConcreteRepo(connection=conn)
    await repo.execute_procedure("myschema.my_proc")
    conn.execute.assert_awaited_once_with("CALL myschema.my_proc()", timeout=None)


@pytest.mark.asyncio
async def test_execute_procedure_with_args_and_timeout():
    conn = AsyncMock()
    conn.execute = AsyncMock()
    repo = ConcreteRepo(connection=conn)
    await repo.execute_procedure("pricing.refresh", ("2024-01-01", "2024-12-31"), timeout=3600)
    conn.execute.assert_awaited_once_with(
        "CALL pricing.refresh($1, $2)", "2024-01-01", "2024-12-31", timeout=3600
    )


@pytest.mark.asyncio
async def test_transaction_returns_connection_transaction():
    conn = MagicMock()
    tx = MagicMock()
    conn.transaction = MagicMock(return_value=tx)
    repo = ConcreteRepo(connection=conn)
    result = repo.transaction()
    conn.transaction.assert_called_once()
    assert result is tx


@pytest.mark.asyncio
async def test_add_listener_delegates():
    conn = AsyncMock()
    repo = ConcreteRepo(connection=conn)
    cb = MagicMock()
    await repo.add_listener("my_channel", cb)
    conn.add_listener.assert_awaited_once_with("my_channel", cb)


@pytest.mark.asyncio
async def test_remove_listener_delegates():
    conn = AsyncMock()
    repo = ConcreteRepo(connection=conn)
    cb = MagicMock()
    await repo.remove_listener("my_channel", cb)
    conn.remove_listener.assert_awaited_once_with("my_channel", cb)
