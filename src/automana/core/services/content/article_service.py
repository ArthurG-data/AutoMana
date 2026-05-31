import re
from uuid import UUID

from automana.core.framework.registry import ServiceRegistry
from automana.core.models.content.article import ArticleCreate, ArticleUpdate
from automana.core.exceptions.service_layer_exceptions.content.content_exceptions import (
    ArticleNotFoundError,
    ArticleValidationError,
)

_WORDS_PER_MINUTE = 230
_ALLOWED_UPDATE_FIELDS = {"title", "excerpt", "body_markdown", "cover_image_url", "tags", "read_minutes"}


def slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s or "article"


def estimate_read_minutes(body_markdown: str) -> int:
    words = len(body_markdown.split())
    return max(1, round(words / _WORDS_PER_MINUTE))


async def _unique_slug(article_repository, title: str) -> str:
    base = slugify(title)
    candidate, n = base, 1
    while await article_repository.exists_slug(candidate):
        n += 1
        candidate = f"{base}-{n}"
    return candidate


@ServiceRegistry.register("content.article.list_public", db_repositories=["article"])
async def list_public_articles(article_repository, limit: int = 20, offset: int = 0, tag: str | None = None):
    return await article_repository.list_published(limit=limit, offset=offset, tag=tag)


@ServiceRegistry.register("content.article.get_public", db_repositories=["article"])
async def get_public_article(article_repository, slug: str):
    article = await article_repository.get_by_slug(slug=slug, published_only=True)
    if not article:
        raise ArticleNotFoundError(f"Article not found: {slug}")
    return article


@ServiceRegistry.register("content.article.list_admin", db_repositories=["article"])
async def list_admin_articles(article_repository, limit: int = 50, offset: int = 0):
    return await article_repository.list_all(limit=limit, offset=offset)


@ServiceRegistry.register("content.article.get_admin", db_repositories=["article"])
async def get_admin_article(article_repository, article_id: UUID):
    article = await article_repository.get_by_id(article_id)
    if not article:
        raise ArticleNotFoundError(f"Article not found: {article_id}")
    return article


@ServiceRegistry.register("content.article.create", db_repositories=["article"])
async def create_article(article_repository, payload: ArticleCreate, user):
    slug = await _unique_slug(article_repository, payload.title)
    return await article_repository.insert_article(
        slug=slug,
        title=payload.title,
        excerpt=payload.excerpt,
        cover_image_url=payload.cover_image_url,
        body_markdown=payload.body_markdown,
        tags=payload.tags,
        read_minutes=estimate_read_minutes(payload.body_markdown),
        author_id=user.unique_id,
    )


@ServiceRegistry.register("content.article.update", db_repositories=["article"])
async def update_article(article_repository, article_id: UUID, payload: ArticleUpdate):
    fields = {k: v for k, v in payload.model_dump(exclude_unset=True).items()
              if k in _ALLOWED_UPDATE_FIELDS}
    if "body_markdown" in fields:
        fields["read_minutes"] = estimate_read_minutes(fields["body_markdown"])
    if not fields:
        raise ArticleValidationError("No updatable fields supplied")
    updated = await article_repository.update_article(article_id, fields)
    if not updated:
        raise ArticleNotFoundError(f"Article not found: {article_id}")
    return updated


@ServiceRegistry.register("content.article.publish", db_repositories=["article"])
async def publish_article(article_repository, article_id: UUID, published: bool):
    updated = await article_repository.update_publish_status(article_id, published)
    if not updated:
        raise ArticleNotFoundError(f"Article not found: {article_id}")
    return updated


@ServiceRegistry.register("content.article.delete", db_repositories=["article"])
async def delete_article(article_repository, article_id: UUID):
    deleted = await article_repository.delete_article(article_id)
    if not deleted:
        raise ArticleNotFoundError(f"Article not found: {article_id}")
    return {"deleted": True, "article_id": str(article_id)}
