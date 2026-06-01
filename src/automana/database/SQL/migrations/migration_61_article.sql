-- migration_61_article.sql
--
-- Adds the editorial "Analysis" articles feature: a new `content` schema with a
-- single `article` table. Articles are authored in-app (Markdown body stored
-- verbatim), publicly readable when status='published'. The Markdown body leaves
-- a clean seam for live data embeds (directive syntax) in a later iteration —
-- no schema change needed then.
--
-- Rollback:
--   DROP TABLE IF EXISTS content.article;
--   DROP SCHEMA IF EXISTS content;

BEGIN;

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

-- Hub query: published articles, newest first.
CREATE INDEX IF NOT EXISTS idx_article_published
    ON content.article (published_at DESC)
    WHERE status = 'published';

GRANT SELECT, INSERT, UPDATE, DELETE ON content.article TO app_celery, app_rw, app_admin;
GRANT SELECT ON content.article TO app_ro;

COMMIT;
