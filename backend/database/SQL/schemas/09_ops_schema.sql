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
  pipeline_name text NOT NULL,
  source_id     bigint NOT NULL REFERENCES ops.sources(id),
  run_key text UNIQUE,
  celery_task_id text, --root task_id if using celery
  started_at    timestamptz DEFAULT now(),
  ended_at      timestamptz,
  status        text CHECK (status IN ('pending','running','success','partial','failed')),
  current_step    text,                        -- e.g. 'download_cards'
  progress        numeric(5,2),                -- 0–100
  error_code      text,
  error_details   jsonb,
  notes           text,
    -- Audit
  created_at      timestamptz DEFAULT now(),
  updated_at      timestamptz DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_ingestion_runs_key
ON ops.ingestion_runs (pipeline_name, source_id, run_key);

CREATE TABLE IF NOT EXISTS ops.ingestion_run_steps (
  id                bigserial PRIMARY KEY,
  ingestion_run_id bigint NOT NULL REFERENCES ops.ingestion_runs(id) ON DELETE CASCADE,
  step_name        text NOT NULL,               -- e.g. 'download_cards'
  started_at       timestamptz DEFAULT now(),
  ended_at         timestamptz,
  status           text CHECK (status IN ('pending','running','success','partial','failed')),
  progress         numeric(5,2),                -- 0–100
  error_code       text,
  error_details    jsonb,
  notes            text,
  UNIQUE (ingestion_run_id, step_name)
);
CREATE INDEX IF NOT EXISTS ix_ingestion_run_steps_run
ON ops.ingestion_run_steps (ingestion_run_id);

CREATE UNIQUE INDEX IF NOT EXISTS ux_run_step_once
ON ops.ingestion_run_steps (ingestion_run_id, step_name);

CREATE TABLE IF NOT EXISTS ops.ingestion_step_metrics (
  ingestion_step_metric_id BIGSERIAL PRIMARY KEY,
  ingestion_run_step_id    BIGINT NOT NULL REFERENCES ops.ingestion_run_steps(id) ON DELETE CASCADE,

  metric_name              TEXT NOT NULL,   -- e.g. items_processed, bytes_downloaded, http_429s
  metric_type              TEXT NOT NULL DEFAULT 'counter', -- counter/gauge/timer
  metric_value_num         DOUBLE PRECISION NULL,
  metric_value_text        TEXT NULL,

  recorded_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_step_metrics_step
ON ops.ingestion_step_metrics (ingestion_run_step_id);

CREATE INDEX IF NOT EXISTS ix_step_metrics_name
ON ops.ingestion_step_metrics (metric_name);


CREATE TABLE ops.ingestion_step_batches (
  id BIGSERIAL PRIMARY KEY,
  ingestion_run_step_id BIGINT NOT NULL REFERENCES ops.ingestion_run_steps(id) ON DELETE CASCADE,
  batch_seq INT NOT NULL,
  range_start BIGINT,
  range_end BIGINT,
  status TEXT CHECK (status IN ('pending','running','success','partial','failed')),
  items_ok INT,
  items_failed INT,
  bytes_processed BIGINT,
  duration_ms INT,
  error_code TEXT,
  error_details JSONB,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (ingestion_run_step_id, batch_seq)
);
CREATE INDEX ON ops.ingestion_step_batches (ingestion_run_step_id, status);
CREATE TABLE IF NOT EXISTS ops.ingestion_run_resources (
  id                bigserial PRIMARY KEY,
  ingestion_run_id bigint NOT NULL REFERENCES ops.ingestion_runs(id) ON DELETE CASCADE,
  resource_version_id bigint NOT NULL REFERENCES ops.resource_versions(id) ON DELETE CASCADE,
  status            text CHECK (status IN ('pending','processed','failed')),
  notes             text,
  UNIQUE (ingestion_run_id, resource_version_id)
);

INSERT INTO ops.sources (name, base_uri, kind, rate_limit_hz)
VALUES ('mtgStock', 'https://api.mtgstocks.com', 'http', 2.0)
ON CONFLICT (name) DO UPDATE
SET base_uri = EXCLUDED.base_uri,
    kind = EXCLUDED.kind,
    rate_limit_hz = EXCLUDED.rate_limit_hz;

WITH src AS (
  SELECT id FROM ops.sources WHERE name = 'mtgStock'
)
INSERT INTO ops.resources (
    source_id, external_type, external_id, canonical_key,
    name, description, api_uri, web_uri, metadata
)
VALUES
  (
    (SELECT id FROM src),
    'print_details', 'prints/{print_id}', 'mtgstock.print.details',
    'MTGStocks print details',
    'JSON details for a print',
    'https://api.mtgstocks.com/prints/{print_id}',
    'https://www.mtgstocks.com/prints/{print_id}',
    '{"format":"json"}'::jsonb
  ),
  (
    (SELECT id FROM src),
    'print_prices', 'prints/{print_id}/prices', 'mtgstock.print.prices',
    'MTGStocks print prices',
    'Price history for a print',
    'https://api.mtgstocks.com/prints/{print_id}/prices',
    'https://www.mtgstocks.com/prints/{print_id}',
    '{"format":"json"}'::jsonb
  )
ON CONFLICT (source_id, external_type, external_id, canonical_key) DO UPDATE
SET name = EXCLUDED.name,
    description = EXCLUDED.description,
    api_uri = EXCLUDED.api_uri,
    web_uri = EXCLUDED.web_uri,
    metadata = EXCLUDED.metadata;
COMMIT;