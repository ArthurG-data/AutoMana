from typing import Optional, List
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class ArticleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    excerpt: str = Field(default="", max_length=500)
    body_markdown: str = Field(default="")
    cover_image_url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class ArticleUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    excerpt: Optional[str] = Field(default=None, max_length=500)
    body_markdown: Optional[str] = None
    cover_image_url: Optional[str] = None
    tags: Optional[List[str]] = None


class Article(BaseModel):
    article_id: UUID
    slug: str
    title: str
    excerpt: str
    cover_image_url: Optional[str] = None
    body_markdown: str
    status: str
    tags: List[str]
    read_minutes: int
    author_id: Optional[UUID] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
