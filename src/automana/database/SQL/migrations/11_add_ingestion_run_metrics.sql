-- ============================================================
-- Migration 11: Add ops.ingestion_run_metrics
--
-- The schema defined ops.ingestion_step_metrics (step-level)
-- but OpsRepository.add_metric() writes to ops.ingestion_run_metrics
-- (run-level). This migration creates the missing table.
--
-- The two tables serve different purposes:
--   ingestion_run_metrics  → one summary value per metric per run
--                            (e.g. total_cards_ingested for the whole pipeline)
--   ingestion_step_metrics → time-series counters per step
--                            (e.g. items_processed ticked every batch)
-- ============================================================

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
