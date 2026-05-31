import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

pytestmark = pytest.mark.service

from automana.core.services.content import article_service
from automana.core.models.content.article import ArticleCreate, ArticleUpdate


def _repo():
    repo = MagicMock()
    repo.list_published = AsyncMock(return_value=[])
    repo.get_by_slug = AsyncMock(return_value=None)
    repo.exists_slug = AsyncMock(return_value=False)
    repo.insert_article = AsyncMock(return_value={"slug": "x"})
    repo.update_article = AsyncMock(return_value={"slug": "x"})
    repo.update_publish_status = AsyncMock(return_value={"slug": "x", "status": "published"})
    repo.delete_article = AsyncMock(return_value=True)
    repo.get_by_id = AsyncMock(return_value={"article_id": "1"})
    return repo


def test_slugify_and_read_minutes():
    assert article_service.slugify("Sheoldred Is a Pillar!") == "sheoldred-is-a-pillar"
    # ~230 wpm, always at least 1
    assert article_service.estimate_read_minutes("word " * 460) == 2
    assert article_service.estimate_read_minutes("") == 1


async def test_get_public_article_raises_when_unpublished_missing():
    repo = _repo()
    repo.get_by_slug = AsyncMock(return_value=None)
    with pytest.raises(ValueError, match="not found"):
        await article_service.get_public_article(article_repository=repo, slug="ghost")
    # public read MUST request published_only=True
    assert repo.get_by_slug.call_args.kwargs["published_only"] is True


async def test_list_public_articles_passes_published_filter():
    repo = _repo()
    await article_service.list_public_articles(article_repository=repo, limit=10, offset=0, tag=None)
    repo.list_published.assert_awaited_once_with(limit=10, offset=0, tag=None)


async def test_create_article_generates_unique_slug_and_read_minutes():
    repo = _repo()
    repo.exists_slug = AsyncMock(side_effect=[True, False])  # first collides, second free
    user = MagicMock(); user.unique_id = uuid4()
    payload = ArticleCreate(title="Hot Take", body_markdown="word " * 230)
    await article_service.create_article(article_repository=repo, payload=payload, user=user)
    kwargs = repo.insert_article.call_args.kwargs
    assert kwargs["slug"] == "hot-take-2"   # de-duplicated
    assert kwargs["read_minutes"] == 1
    assert kwargs["author_id"] == user.unique_id


async def test_publish_article_raises_for_missing():
    repo = _repo()
    repo.update_publish_status = AsyncMock(return_value=None)
    with pytest.raises(ValueError, match="not found"):
        await article_service.publish_article(article_repository=repo, article_id=uuid4(), published=True)
