-- migration_36: Add pricing.mv_card_price_spark materialized view.
--
-- Pre-computes per-card-version current price, 1d/7d/30d % changes, and a
-- 7-point sparkline for the standard TCGPlayer NM English Non-Foil market
-- (transaction_type_id=1, condition_id=1, language_id=1, finish_id=1).
--
-- Replaces the expensive GROUP-BY run on every search page: Python now reads
-- from this view instead. Refresh is driven by the daily Celery beat schedule
-- via CALL pricing.refresh_card_price_spark().
--
-- Objects created:
--   1. pricing.mv_card_price_spark  (MATERIALIZED VIEW WITH DATA)
--   2. idx_mv_card_price_spark_cv   (UNIQUE index — required for CONCURRENTLY refresh)
--   3. pricing.refresh_card_price_spark()  (SECURITY DEFINER procedure)
--   4. SELECT grant to app_celery, app_rw, app_admin, app_ro
--   5. EXECUTE grant on procedure to app_celery, app_rw, app_admin

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Materialized view
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW pricing.mv_card_price_spark AS
WITH daily AS (
    SELECT
        ppd.card_version_id,
        ppd.price_date,
        COALESCE(AVG(ppd.list_avg_cents), AVG(ppd.sold_avg_cents)) / 100.0 AS avg_price
    FROM pricing.print_price_daily ppd
    WHERE ppd.transaction_type_id = 1
      AND ppd.condition_id        = 1
      AND ppd.language_id         = 1
      AND ppd.finish_id           = 1
      AND ppd.price_date          > CURRENT_DATE - 365  -- exclusive: mirrors original runtime query
    GROUP BY ppd.card_version_id, ppd.price_date
    HAVING COALESCE(AVG(ppd.list_avg_cents), AVG(ppd.sold_avg_cents)) IS NOT NULL
),
ranked AS (
    SELECT
        card_version_id,
        price_date,
        avg_price,
        ROW_NUMBER() OVER (PARTITION BY card_version_id ORDER BY price_date DESC) AS rn
    FROM daily
),
current_prices AS (
    SELECT card_version_id, price_date AS latest_price_date, avg_price AS current_price
    FROM ranked
    WHERE rn = 1
),
spark_rows AS (
    SELECT
        card_version_id,
        ARRAY_AGG(avg_price ORDER BY price_date ASC) AS spark
    FROM ranked
    WHERE rn <= 7
    GROUP BY card_version_id
)
SELECT
    cp.card_version_id,
    cp.current_price                                                              AS price,
    CASE
        WHEN d1.avg_price IS NULL OR d1.avg_price = 0 THEN 0.0
        ELSE ROUND(((cp.current_price - d1.avg_price) / d1.avg_price * 100)::numeric, 2)::float
    END                                                                           AS price_change_1d,
    CASE
        WHEN d7.avg_price IS NULL OR d7.avg_price = 0 THEN 0.0
        ELSE ROUND(((cp.current_price - d7.avg_price) / d7.avg_price * 100)::numeric, 2)::float
    END                                                                           AS price_change_7d,
    CASE
        WHEN d30.avg_price IS NULL OR d30.avg_price = 0 THEN 0.0
        ELSE ROUND(((cp.current_price - d30.avg_price) / d30.avg_price * 100)::numeric, 2)::float
    END                                                                           AS price_change_30d,
    COALESCE(sr.spark, ARRAY[cp.current_price])                                  AS spark
FROM current_prices cp
LEFT JOIN daily d1
    ON d1.card_version_id = cp.card_version_id
   AND d1.price_date      = cp.latest_price_date - INTERVAL '1 day'
LEFT JOIN daily d7
    ON d7.card_version_id = cp.card_version_id
   AND d7.price_date      = cp.latest_price_date - INTERVAL '7 days'
LEFT JOIN daily d30
    ON d30.card_version_id = cp.card_version_id
   AND d30.price_date      = cp.latest_price_date - INTERVAL '30 days'
LEFT JOIN spark_rows sr ON sr.card_version_id = cp.card_version_id
WITH DATA;

-- ---------------------------------------------------------------------------
-- 2. Unique index (required for REFRESH MATERIALIZED VIEW CONCURRENTLY)
-- ---------------------------------------------------------------------------
CREATE UNIQUE INDEX idx_mv_card_price_spark_cv
    ON pricing.mv_card_price_spark (card_version_id);

-- ---------------------------------------------------------------------------
-- 3. SECURITY DEFINER refresh procedure
--    app_celery is app_rw, not the view owner — SECURITY DEFINER lets it
--    call REFRESH without needing ownership of the view.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE pricing.refresh_card_price_spark()
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pricing, pg_catalog
AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY pricing.mv_card_price_spark;
    RAISE NOTICE 'pricing.mv_card_price_spark refreshed at %', now();
END;
$$;

GRANT EXECUTE ON PROCEDURE pricing.refresh_card_price_spark()
    TO app_celery, app_rw, app_admin;

-- ---------------------------------------------------------------------------
-- 4. Read grants
-- ---------------------------------------------------------------------------
GRANT SELECT ON pricing.mv_card_price_spark
    TO app_celery, app_rw, app_admin, app_ro;

COMMIT;
