-- migration_25_create_reporting_schema.sql
--
-- Creates the reporting schema with hourly_metrics table for tracking API request
-- and Celery task metrics. Includes columns for request counts, error rates, cache hits,
-- and response time percentiles.

BEGIN;

-- Create the reporting schema
CREATE SCHEMA IF NOT EXISTS reporting;

-- Create the hourly_metrics table
CREATE TABLE reporting.hourly_metrics (
    id BIGSERIAL PRIMARY KEY,

    -- Time-based grouping
    hour TIMESTAMP NOT NULL,

    -- Metric type: 'api_request' or 'celery_task'
    metric_type VARCHAR(20) NOT NULL,

    -- API-specific: endpoint path (NULL for Celery)
    endpoint VARCHAR(255),

    -- Celery-specific: task name (NULL for API)
    task_name VARCHAR(255),

    -- API-specific: HTTP status code (NULL for Celery)
    status_code SMALLINT,

    -- Request/Task counts
    request_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    cache_hit_count INTEGER DEFAULT 0,

    -- API response time percentiles (NULL for Celery)
    response_time_p95 FLOAT,
    response_time_median FLOAT,
    response_time_max FLOAT,

    -- Celery-specific counters (NULL for API)
    celery_success_count INTEGER,
    celery_failure_count INTEGER,

    -- Derived metrics (0-1 floats)
    error_rate FLOAT,
    cache_hit_rate FLOAT,
    celery_success_rate FLOAT,

    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),

    -- Unique constraint: one row per (hour, metric_type, endpoint, task_name, status_code) tuple
    CONSTRAINT uk_hourly_metrics_unique UNIQUE (hour, metric_type, endpoint, task_name, status_code)
);

-- Indexes for query performance
CREATE INDEX idx_hourly_metrics_hour ON reporting.hourly_metrics (hour DESC);
CREATE INDEX idx_hourly_metrics_endpoint ON reporting.hourly_metrics (endpoint);
CREATE INDEX idx_hourly_metrics_task_name ON reporting.hourly_metrics (task_name);

-- Grant permissions to app roles
GRANT USAGE ON SCHEMA reporting TO app_backend, app_celery;
GRANT SELECT, INSERT, UPDATE, DELETE ON reporting.hourly_metrics TO app_backend, app_celery;
GRANT USAGE, SELECT ON SEQUENCE reporting.hourly_metrics_id_seq TO app_backend, app_celery;

COMMIT;
