import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

pytestmark = pytest.mark.repository

from automana.core.repositories.content.article_repository import ArticleRepository


def _repo():
    repo = ArticleRepository(connection=AsyncMock(), executor=None)
    repo.execute_query = AsyncMock()
    repo.execute_command = AsyncMock()
    return repo


async def test_list_published_filters_status_and_paginates():
    repo = _repo()
    repo.execute_query.return_value = [{"slug": "a"}]
    rows = await repo.list_published(limit=10, offset=0, tag=None)
    sql, values = repo.execute_query.call_args.args
    assert "status = 'published'" in sql
    assert values == (10, 0)
    assert rows == [{"slug": "a"}]


async def test_list_published_adds_tag_filter():
    repo = _repo()
    repo.execute_query.return_value = []
    await repo.list_published(limit=5, offset=0, tag="spec")
    sql, values = repo.execute_query.call_args.args
    assert "$3 = ANY(tags)" in sql
    assert values == (5, 0, "spec")


async def test_get_by_slug_published_only_appends_status_clause():
    repo = _repo()
    repo.execute_query.return_value = [{"slug": "x", "status": "published"}]
    result = await repo.get_by_slug("x", published_only=True)
    sql, values = repo.execute_query.call_args.args
    assert "status = 'published'" in sql
    assert values == ("x",)
    assert result == {"slug": "x", "status": "published"}


async def test_get_by_slug_returns_none_when_missing():
    repo = _repo()
    repo.execute_query.return_value = []
    assert await repo.get_by_slug("nope", published_only=True) is None


async def test_insert_article_returns_row():
    repo = _repo()
    new_id = uuid4()
    repo.execute_query.return_value = [{"article_id": new_id, "slug": "t"}]
    result = await repo.insert_article(
        slug="t", title="T", excerpt="e", cover_image_url=None,
        body_markdown="# hi", tags=["spec"], read_minutes=2, author_id=uuid4(),
    )
    sql, _ = repo.execute_query.call_args.args
    assert sql.strip().upper().startswith("INSERT INTO CONTENT.ARTICLE")
    assert result["slug"] == "t"


async def test_update_publish_status_sets_published_at_on_publish():
    repo = _repo()
    repo.execute_query.return_value = [{"status": "published"}]
    await repo.update_publish_status(article_id=uuid4(), published=True)
    sql, _ = repo.execute_query.call_args.args
    assert "published_at = now()" in sql
    assert "status = 'published'" in sql
