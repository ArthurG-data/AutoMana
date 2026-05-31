from typing import Optional, List
from uuid import UUID

from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository

_COLUMNS = """article_id, slug, title, excerpt, cover_image_url, body_markdown,
              status, tags, read_minutes, author_id, published_at,
              created_at, updated_at"""


class ArticleRepository(AbstractRepository):
    """DB access for content.article. All queries go through the AbstractRepository
    wrappers (execute_query/execute_command). Service-facing methods follow CQS
    naming; the ABC's generic get/add/update/delete/list are stubbed (this repo
    exposes explicit, intention-revealing methods instead)."""

    def __init__(self, connection, executor=None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "ArticleRepository"

    # ---- queries (reads) -------------------------------------------------
    async def list_published(self, limit: int, offset: int, tag: Optional[str]) -> List[dict]:
        tag_clause = "AND $3 = ANY(tags)" if tag else ""
        query = f"""
            SELECT {_COLUMNS}
            FROM content.article
            WHERE status = 'published'
            {tag_clause}
            ORDER BY published_at DESC
            LIMIT $1 OFFSET $2;
        """
        values = (limit, offset, tag) if tag else (limit, offset)
        rows = await self.execute_query(query, values)
        return [dict(r) for r in rows]

    async def list_all(self, limit: int, offset: int) -> List[dict]:
        query = f"""
            SELECT {_COLUMNS}
            FROM content.article
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2;
        """
        rows = await self.execute_query(query, (limit, offset))
        return [dict(r) for r in rows]

    async def get_by_slug(self, slug: str, published_only: bool) -> Optional[dict]:
        status_clause = "AND status = 'published'" if published_only else ""
        query = f"""
            SELECT {_COLUMNS}
            FROM content.article
            WHERE slug = $1 {status_clause};
        """
        rows = await self.execute_query(query, (slug,))
        return dict(rows[0]) if rows else None

    async def get_by_id(self, article_id: UUID) -> Optional[dict]:
        query = f"SELECT {_COLUMNS} FROM content.article WHERE article_id = $1;"
        rows = await self.execute_query(query, (article_id,))
        return dict(rows[0]) if rows else None

    async def exists_slug(self, slug: str) -> bool:
        rows = await self.execute_query(
            "SELECT 1 FROM content.article WHERE slug = $1;", (slug,)
        )
        return bool(rows)

    # ---- commands (writes) ----------------------------------------------
    async def insert_article(self, slug, title, excerpt, cover_image_url,
                             body_markdown, tags, read_minutes, author_id) -> Optional[dict]:
        query = f"""
            INSERT INTO content.article
                (slug, title, excerpt, cover_image_url, body_markdown,
                 tags, read_minutes, author_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING {_COLUMNS};
        """
        rows = await self.execute_query(
            query,
            (slug, title, excerpt, cover_image_url, body_markdown,
             tags, read_minutes, author_id),
        )
        return dict(rows[0]) if rows else None

    async def update_article(self, article_id: UUID, fields: dict) -> Optional[dict]:
        # Build a dynamic SET clause from a whitelisted dict (keys validated by the service).
        keys = list(fields.keys())
        set_clause = ", ".join(f"{k} = ${i + 1}" for i, k in enumerate(keys))
        query = f"""
            UPDATE content.article
            SET {set_clause}, updated_at = now()
            WHERE article_id = ${len(keys) + 1}
            RETURNING {_COLUMNS};
        """
        values = (*fields.values(), article_id)
        rows = await self.execute_query(query, values)
        return dict(rows[0]) if rows else None

    async def update_publish_status(self, article_id: UUID, published: bool) -> Optional[dict]:
        if published:
            query = f"""
                UPDATE content.article
                SET status = 'published', published_at = now(), updated_at = now()
                WHERE article_id = $1
                RETURNING {_COLUMNS};
            """
        else:
            query = f"""
                UPDATE content.article
                SET status = 'draft', updated_at = now()
                WHERE article_id = $1
                RETURNING {_COLUMNS};
            """
        rows = await self.execute_query(query, (article_id,))
        return dict(rows[0]) if rows else None

    async def delete_article(self, article_id: UUID) -> bool:
        result = await self.execute_command(
            "DELETE FROM content.article WHERE article_id = $1;", (article_id,)
        )
        return result != "DELETE 0"

    # ---- ABC contract (intentionally unused; explicit methods above) -----
    async def get(self, id):       raise NotImplementedError
    async def add(self, item):     raise NotImplementedError
    async def update(self, item):  raise NotImplementedError
    async def delete(self, id):    raise NotImplementedError
    async def list(self, items):   raise NotImplementedError
