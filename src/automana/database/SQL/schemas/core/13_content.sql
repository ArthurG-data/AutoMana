-- 13_content.sql
-- Editorial articles feature.

CREATE SCHEMA IF NOT EXISTS content;
GRANT USAGE ON SCHEMA content TO app_celery, app_rw, app_admin, app_ro;

CREATE TABLE IF NOT EXISTS content.article (
    article_id       UUID        NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    slug             TEXT        NOT NULL UNIQUE,
    title            TEXT        NOT NULL,
    excerpt          TEXT        NOT NULL DEFAULT '',
    cover_image_url  TEXT,
    body_markdown    TEXT        NOT NULL DEFAULT '',
    status           TEXT        NOT NULL DEFAULT 'draft'
                                 CHECK (status IN ('draft', 'published')),
    tags             TEXT[]      NOT NULL DEFAULT '{}',
    read_minutes     INTEGER     NOT NULL DEFAULT 1,
    author_id        UUID        REFERENCES user_management.users(unique_id),
    published_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_article_published
    ON content.article (published_at DESC)
    WHERE status = 'published';

GRANT SELECT, INSERT, UPDATE, DELETE ON content.article TO app_celery, app_rw, app_admin;
GRANT SELECT ON content.article TO app_ro;
