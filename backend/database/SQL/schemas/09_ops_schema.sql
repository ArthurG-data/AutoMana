BEGIN;
CREATE SCHEMA IF NOT EXISTS ops;
CREATE TABLE IF NOT EXISTS ops.sources (
  id            bigserial PRIMARY KEY,
  name          text UNIQUE NOT NULL,     -- e.g. 'scryfall', 'tcgplayer'
  base_uri      text,
  kind          text,                     -- 'http', 's3', 'ftp', etc.
  rate_limit_hz numeric,                  -- optional governance
  created_at    timestamptz DEFAULT now(),
  updated_at    timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.resources (
  id                bigserial PRIMARY KEY,
  source_id         bigint NOT NULL REFERENCES ops.sources(id),
  external_type     text NOT NULL,
  external_id       text,
  canonical_key     text,
  name              text,
  description       text,
  api_uri           text,
  web_uri           text,
  metadata          jsonb,
  updated_at_source timestamptz,
  created_at        timestamptz DEFAULT now(),
  CHECK (external_id IS NOT NULL OR canonical_key IS NOT NULL)
);
-------------------------
--select the ressources, select the latest version, then if new version, insert new version

-- add a UNIQUE INDEX (expressions are allowed in indexes)
CREATE UNIQUE INDEX IF NOT EXISTS ux_resources_source_type_natkey
ON ops.resources (source_id, external_type,  external_id, canonical_key);

CREATE TABLE IF NOT EXISTS ops.resource_versions (
  id                bigserial PRIMARY KEY,
  resource_id       bigint NOT NULL REFERENCES ops.resources(id) ON DELETE CASCADE,
  download_uri      text NOT NULL,        -- the ephemeral file URL you fetched
  content_type      text,
  content_encoding  text,
  bytes             bigint,
  etag              text,
  last_modified     timestamptz,
  sha256            text,                 -- optional but great for integrity/dedup
  status            text NOT NULL CHECK (status IN ('downloaded','processed','failed')),
  error             text,
  created_at        timestamptz DEFAULT now(),
  UNIQUE (resource_id, sha256)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_resource_versions_natkey
ON ops.resource_versions(resource_id, download_uri, last_modified);

CREATE TABLE IF NOT EXISTS ops.ingestion_runs (
  id            bigserial PRIMARY KEY,
  source_id     bigint NOT NULL REFERENCES ops.sources(id),
  started_at    timestamptz DEFAULT now(),
  ended_at      timestamptz,
  status        text CHECK (status IN ('running','success','partial','failed')),
  notes         text
);
CREATE TABLE IF NOT EXISTS ops.ingestion_run_resources (
  id                bigserial PRIMARY KEY,
  ingestion_run_id bigint NOT NULL REFERENCES ops.ingestion_runs(id) ON DELETE CASCADE,
  resource_version_id bigint NOT NULL REFERENCES ops.resource_versions(id) ON DELETE CASCADE,
  status            text CHECK (status IN ('pending','processed','failed')),
  notes             text,
  UNIQUE (ingestion_run_id, resource_version_id)
);
COMMIT;