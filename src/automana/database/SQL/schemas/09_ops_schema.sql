BEGIN;
CREATE SCHEMA IF NOT EXISTS ops;

-- ============================================================
-- GROUP 1: SOURCE REGISTRY
-- Static(ish) configuration describing external data sources
-- and the named resources they expose.
--
--   sources          → one row per external system (scryfall, mtgstock, …)
--   resources        → named endpoints/files within a source
--   resource_versions→ each distinct download of a resource (tracks URI + hash)
-- ============================================================

CREATE TABLE IF NOT EXISTS ops.sources (
  id            bigserial PRIMARY KEY,
  name          text UNIQUE NOT NULL,     -- e.g. 'scryfall', 'tcgplayer'
  base_uri      text,
  kind          text,                     -- 'http', 's3', 'ftp', etc.
  rate_limit_hz numeric,                  -- optional request-rate governance
  created_at    timestamptz DEFAULT now(),
  updated_at    timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.resources (
  id                bigserial PRIMARY KEY,
  source_id         bigint NOT NULL REFERENCES ops.sources(id),
  external_type     text NOT NULL,        -- e.g. 'bulk_data', 'sets', 'prices'
  external_id       text,                 -- provider's own identifier
  canonical_key     text,                 -- internal stable key
  name              text,
  description       text,
  api_uri           text,                 -- current endpoint URI
  web_uri           text,
  metadata          jsonb,
  updated_at_source timestamptz,
  created_at        timestamptz DEFAULT now(),
  CHECK (external_id IS NOT NULL OR canonical_key IS NOT NULL)
);

-- Full natural key: a resource is unique per (source, type, external_id, canonical_key).
-- NULLs in `canonical_key` don't collide with each other in the default index,
-- so this covers the (…, canonical_key IS NOT NULL) case cleanly but doesn't
-- prevent duplicates when canonical_key IS NULL — the partial index below
-- handles that case.
CREATE UNIQUE INDEX IF NOT EXISTS ux_resources_source_type_natkey
ON ops.resources (source_id, external_type, external_id, canonical_key);

-- Partial unique index matching the Scryfall bulk upsert's ON CONFLICT target
-- in scryfall_data.py (`ON CONFLICT (source_id, external_type, external_id)
-- WHERE canonical_key IS NULL`). Without this the upsert errors with
-- "there is no unique or exclusion constraint matching the ON CONFLICT
-- specification" on any run where canonical_key is NULL.
CREATE UNIQUE INDEX IF NOT EXISTS ux_resources_no_canonical_key
ON ops.resources (source_id, external_type, external_id)
WHERE canonical_key IS NULL;

CREATE TABLE IF NOT EXISTS ops.resource_versions (
  id                bigserial PRIMARY KEY,
  resource_id       bigint NOT NULL REFERENCES ops.resources(id) ON DELETE CASCADE,
  download_uri      text NOT NULL,        -- ephemeral URL for this specific download
  content_type      text,
  content_encoding  text,
  bytes             bigint,
  etag              text,
  last_modified     timestamptz,
  sha256            text,                 -- integrity check / dedup key
  status            text NOT NULL CHECK (status IN ('downloaded','processed','failed')),
  error             text,
  created_at        timestamptz DEFAULT now(),
  UNIQUE (resource_id, sha256)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_resource_versions_natkey
ON ops.resource_versions(resource_id, download_uri, last_modified);


-- ============================================================
-- GROUP 2: PIPELINE EXECUTION LOG
-- High-write tables that track every pipeline run, its steps,
-- per-run summary metrics, per-step detail metrics, and
-- per-step batch-level counters.
--
--   ingestion_runs         → one row per pipeline execution
--   ingestion_run_steps    → one row per named step within a run
--   ingestion_run_metrics  → summary key/value metrics at run level
--   ingestion_step_metrics → fine-grained metrics at step level
--   ingestion_step_batches → batch counters for chunked steps (e.g. card import)
--   ingestion_run_resources→ links a run to the resource_versions it consumed
-- ============================================================

CREATE TABLE IF NOT EXISTS ops.ingestion_runs (
  id             bigserial PRIMARY KEY,
  pipeline_name  text NOT NULL,
  source_id      bigint NOT NULL REFERENCES ops.sources(id),
  run_key        text UNIQUE,            -- idempotency key, e.g. 'scryfall_daily:2026-03-29'
  celery_task_id text,                   -- root Celery task id for correlation
  started_at     timestamptz DEFAULT now(),
  ended_at       timestamptz,
  status         text CHECK (status IN ('pending','running','success','partial','failed')),
  current_step   text,                   -- last active step name
  progress       numeric(5,2),           -- 0–100 overall progress
  error_code     text,
  error_details  jsonb,
  notes          text,
  created_at     timestamptz DEFAULT now(),
  updated_at     timestamptz DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ingestion_runs_key
ON ops.ingestion_runs (pipeline_name, source_id, run_key);

CREATE TABLE IF NOT EXISTS ops.ingestion_run_steps (
  id               bigserial PRIMARY KEY,
  ingestion_run_id bigint NOT NULL REFERENCES ops.ingestion_runs(id) ON DELETE CASCADE,
  step_name        text NOT NULL,        -- e.g. 'download_sets', 'process_large_cards_json'
  started_at       timestamptz DEFAULT now(),
  ended_at         timestamptz,
  status           text CHECK (status IN ('pending','running','success','partial','failed')),
  progress         numeric(5,2),         -- 0–100 step-level progress
  error_code       text,
  error_details    jsonb,
  notes            text,
  UNIQUE (ingestion_run_id, step_name)
);

CREATE INDEX IF NOT EXISTS ix_ingestion_run_steps_run
ON ops.ingestion_run_steps (ingestion_run_id);

-- Run-level summary metrics (one value per metric name per run).
-- Written by OpsRepository.add_metric().
-- Use for totals you want to query across runs (e.g. total cards ingested today).
CREATE TABLE IF NOT EXISTS ops.ingestion_run_metrics (
  id                 bigserial PRIMARY KEY,
  ingestion_run_id   bigint NOT NULL REFERENCES ops.ingestion_runs(id) ON DELETE CASCADE,
  metric_name        text NOT NULL,      -- e.g. 'total_cards', 'total_sets', 'bytes_downloaded'
  metric_value_num   double precision,
  metric_value_text  text,
  recorded_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (ingestion_run_id, metric_name)
);

CREATE INDEX IF NOT EXISTS ix_run_metrics_run
ON ops.ingestion_run_metrics (ingestion_run_id);

CREATE INDEX IF NOT EXISTS ix_run_metrics_name
ON ops.ingestion_run_metrics (metric_name);

-- Step-level fine-grained metrics (multiple values per metric name per step).
-- Use for time-series counters within a step (e.g. items_processed per batch tick).
CREATE TABLE IF NOT EXISTS ops.ingestion_step_metrics (
  id                    bigserial PRIMARY KEY,
  ingestion_run_step_id bigint NOT NULL REFERENCES ops.ingestion_run_steps(id) ON DELETE CASCADE,
  metric_name           text NOT NULL,   -- e.g. 'items_processed', 'bytes_downloaded', 'http_429s'
  metric_type           text NOT NULL DEFAULT 'counter', -- counter / gauge / timer
  metric_value_num      double precision,
  metric_value_text     text,
  recorded_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_step_metrics_step
ON ops.ingestion_step_metrics (ingestion_run_step_id);

CREATE INDEX IF NOT EXISTS ix_step_metrics_name
ON ops.ingestion_step_metrics (metric_name);

-- Batch-level counters for steps that process data in chunks (e.g. card import).
-- Each row is one batch: how many succeeded, failed, bytes processed, duration.
CREATE TABLE IF NOT EXISTS ops.ingestion_step_batches (
  id                    bigserial PRIMARY KEY,
  ingestion_run_step_id bigint NOT NULL REFERENCES ops.ingestion_run_steps(id) ON DELETE CASCADE,
  batch_seq             int NOT NULL,
  range_start           bigint,
  range_end             bigint,
  status                text CHECK (status IN ('pending','running','success','partial','failed')),
  items_ok              int,
  items_failed          int,
  bytes_processed       bigint,
  duration_ms           int,
  error_code            text,
  error_details         jsonb,
  created_at            timestamptz DEFAULT now(),
  UNIQUE (ingestion_run_step_id, batch_seq)
);

CREATE INDEX IF NOT EXISTS ix_step_batches_step
ON ops.ingestion_step_batches (ingestion_run_step_id, status);

-- Links a pipeline run to the specific resource versions it consumed.
-- Enables traceability: which file version was processed in which run.
CREATE TABLE IF NOT EXISTS ops.ingestion_run_resources (
  id                  bigserial PRIMARY KEY,
  ingestion_run_id    bigint NOT NULL REFERENCES ops.ingestion_runs(id) ON DELETE CASCADE,
  resource_version_id bigint NOT NULL REFERENCES ops.resource_versions(id) ON DELETE CASCADE,
  status              text CHECK (status IN ('pending','processed','failed')),
  notes               text,
  UNIQUE (ingestion_run_id, resource_version_id)
);


-- ============================================================
-- GROUP 3: CROSS-SYSTEM ID MAPPING
-- Resolves card identifiers across external providers.
-- NOTE: This table is MTGStock-specific. It lives here because
-- it is populated during ingestion runs, but its content is
-- persistent reference data — not ephemeral ops data.
-- Consider moving to card_catalog schema in a future migration.
-- ============================================================

CREATE TABLE IF NOT EXISTS ops.ingestion_ids_mapping (
  id               serial PRIMARY KEY,
  -- Must be BIGINT to match ops.ingestion_runs.id (bigserial). A plain INT
  -- FK would refuse rows once run ids exceed 2^31 and could silently error.
  ingestion_run_id BIGINT NOT NULL REFERENCES ops.ingestion_runs(id) ON DELETE CASCADE,
  mtgstock_id      bigint NOT NULL,
  scryfall_id      uuid,
  multiverse_id    bigint,
  tcg_id           bigint,
  created_at       timestamptz DEFAULT now(),
  UNIQUE (ingestion_run_id, mtgstock_id)
);

CREATE INDEX IF NOT EXISTS idx_ingestion_ids_mapping_run
ON ops.ingestion_ids_mapping (ingestion_run_id);

CREATE INDEX IF NOT EXISTS idx_ingestion_ids_mapping_scryfall
ON ops.ingestion_ids_mapping (scryfall_id);

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


-- ============================================================
-- Scryfall source + bulk_data resource
--
-- Read by `staging.scryfall.get_bulk_data_uri` → OpsRepository
-- .get_bulk_data_uri() via the query:
--   SELECT r.api_uri FROM ops.resources r
--   JOIN ops.sources s ON s.kind='http' AND s.name='scryfall'
--                     AND r.external_type='bulk_data'
-- Without this row the Scryfall pipeline fails on its first step.
-- ============================================================

INSERT INTO ops.sources (name, base_uri, kind, rate_limit_hz)
VALUES ('scryfall', 'https://api.scryfall.com', 'http', 10.0)
ON CONFLICT (name) DO UPDATE
SET base_uri = EXCLUDED.base_uri,
    kind = EXCLUDED.kind,
    rate_limit_hz = EXCLUDED.rate_limit_hz;

WITH src AS (
  SELECT id FROM ops.sources WHERE name = 'scryfall'
)
INSERT INTO ops.resources (
    source_id, external_type, external_id, canonical_key,
    name, description, api_uri, web_uri, metadata
)
VALUES
  (
    (SELECT id FROM src),
    'bulk_data', 'bulk-data', 'scryfall.bulk_data',
    'Scryfall bulk data',
    'Scryfall bulk data catalog endpoint (lists all bulk data manifests).',
    'https://api.scryfall.com/bulk-data',
    'https://scryfall.com/docs/api/bulk-data',
    '{"format":"json"}'::jsonb
  )
ON CONFLICT (source_id, external_type, external_id, canonical_key) DO UPDATE
SET name = EXCLUDED.name,
    description = EXCLUDED.description,
    api_uri = EXCLUDED.api_uri,
    web_uri = EXCLUDED.web_uri,
    metadata = EXCLUDED.metadata;


-- ============================================================
-- MTGJson source + all_printings resource
--
-- Read by `staging.mtgjson.check_version` via
-- OpsRepository.get_mtgjson_resource_version() /
-- .upsert_mtgjson_resource_version(), which filter on
-- canonical_key = 'mtgjson.all_printings'. Seeded here so the
-- version gate works on a fresh rebuild without manual inserts.
-- ============================================================

INSERT INTO ops.sources (name, base_uri, kind, rate_limit_hz)
VALUES ('mtgjson', 'https://mtgjson.com/api/v5', 'http', 2.0)
ON CONFLICT (name) DO UPDATE
SET base_uri = EXCLUDED.base_uri,
    kind = EXCLUDED.kind,
    rate_limit_hz = EXCLUDED.rate_limit_hz;

WITH src AS (
  SELECT id FROM ops.sources WHERE name = 'mtgjson'
)
INSERT INTO ops.resources (
    source_id, external_type, external_id, canonical_key,
    name, description, api_uri, web_uri, metadata
)
VALUES
  (
    (SELECT id FROM src),
    'catalog', 'AllPrintings', 'mtgjson.all_printings',
    'MTGJson AllPrintings catalog',
    'Version metadata for the MTGJson card catalog (Meta.json).',
    'https://mtgjson.com/api/v5/Meta.json',
    'https://mtgjson.com/',
    '{"format":"json"}'::jsonb
  )
ON CONFLICT (source_id, external_type, external_id, canonical_key) DO UPDATE
SET name = EXCLUDED.name,
    description = EXCLUDED.description,
    api_uri = EXCLUDED.api_uri,
    web_uri = EXCLUDED.web_uri,
    metadata = EXCLUDED.metadata;

-- ============================================================
-- ops.pipeline_health_snapshot
--
-- One row per (run_id, check_set). Captures every ops.integrity.*
-- service result so HealthAlertService can diff status transitions
-- across runs and alert Discord only on changes.
-- ============================================================
CREATE TABLE IF NOT EXISTS ops.pipeline_health_snapshot (
    id              bigserial PRIMARY KEY,
    run_id          uuid        NOT NULL,
    captured_at     timestamptz NOT NULL DEFAULT now(),
    check_set       text        NOT NULL,
    pipeline        text        NOT NULL,
    status          text        NOT NULL CHECK (status IN ('ok','warn','error')),
    error_count     int         NOT NULL,
    warn_count      int         NOT NULL,
    total_checks    int         NOT NULL,
    report          jsonb       NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pipeline_health_snapshot_check_set_captured_at
    ON ops.pipeline_health_snapshot (check_set, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_pipeline_health_snapshot_run_id
    ON ops.pipeline_health_snapshot (run_id);

COMMIT;