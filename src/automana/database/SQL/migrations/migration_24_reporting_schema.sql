-- Migration: Create reporting schema and hourly_metrics table
-- Purpose: Support metrics collection and reporting for API and Celery tasks

BEGIN;

-- Create reporting schema
CREATE SCHEMA IF NOT EXISTS reporting;

-- Create hourly_metrics table
CREATE TABLE IF NOT EXISTS reporting.hourly_metrics (
    id SERIAL PRIMARY KEY,
    hour BIGINT NOT NULL,
    metric_type VARCHAR(50) NOT NULL,
    endpoint VARCHAR(255),
    task_name VARCHAR(255),
    status_code SMALLINT,
    request_count INT DEFAULT 0,
    error_count INT DEFAULT 0,
    cache_hit_count INT DEFAULT 0,
    response_time_p95 FLOAT,
    response_time_median FLOAT,
    response_time_max FLOAT,
    celery_success_count INT DEFAULT 0,
    celery_failure_count INT DEFAULT 0,
    error_rate FLOAT,
    cache_hit_rate FLOAT,
    celery_success_rate FLOAT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (hour, metric_type, endpoint, task_name, status_code)
);

-- Create indexes for efficient querying
CREATE INDEX idx_hourly_metrics_hour ON reporting.hourly_metrics (hour DESC);
CREATE INDEX idx_hourly_metrics_metric_type ON reporting.hourly_metrics (metric_type);
CREATE INDEX idx_hourly_metrics_endpoint ON reporting.hourly_metrics (endpoint);
CREATE INDEX idx_hourly_metrics_task_name ON reporting.hourly_metrics (task_name);
CREATE INDEX idx_hourly_metrics_created_at ON reporting.hourly_metrics (created_at DESC);

COMMIT;
