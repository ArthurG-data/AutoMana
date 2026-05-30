-- migration_59_usd_market_spark.sql
--
-- Two related fixes around the US-market price view:
--
-- 1. Correct Manapool's currency: EUR -> USD.
--    migration_34 registered ('manapool', 'Manapool', 'EUR'), but manapool.com
--    is a US marketplace that quotes USD. The EUR label was a copy-paste from
--    the cardmarket row. Manapool currently has 0 rows in source_product /
--    price_observation / print_price_{daily,weekly,latest}, so this flip
--    re-interprets no existing data — it just stops future Manapool prices from
--    being mislabeled EUR everywhere price_source.currency_code is read.
--
-- 2. Scope pricing.mv_card_price_spark to USD sources only.
--    The view (migration_36) is the "US market" composite that drives the
--    search page (TCGplayer, Manapool, and eBay once integrated). Its `daily`
--    CTE averaged list_avg_cents across ALL sources for a card/day without any
--    source/currency restriction. This was actively wrong, not latent: at the
--    time of this migration the view's footprint (tx=1,cond=1,lang=1,finish=1)
--    drew rows from cardmarket (EUR, ~14.2M ppd rows) and cardhoarder (TIX,
--    ~234k rows) alongside the USD sources (mtgstocks, tcg, manapool,
--    cardkingdom, cardsphere) — so EUR/TIX cents were averaged with USD cents
--    and presented as a dollar price. The USD filter restricts the composite to
--    the US market (tcg + manapool today, eBay once integrated) and excludes the
--    EUR/TIX sources.
--
-- A materialized view cannot be CREATE OR REPLACE-d when its definition
-- changes, so the MV is dropped and recreated. Dropping it also drops its
-- unique index and SELECT grants, which are reissued below. The refresh
-- procedure pricing.refresh_card_price_spark() references the view by name and
-- remains valid.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Manapool currency correction
-- ---------------------------------------------------------------------------
UPDATE pricing.price_source
SET    currency_code = 'USD',
       updated_at    = now()
WHERE  code = 'manapool'
  AND  currency_code <> 'USD';

-- ---------------------------------------------------------------------------
-- 2. Rebuild mv_card_price_spark with a USD-only source filter
-- ---------------------------------------------------------------------------
DROP MATERIALIZED VIEW IF EXISTS pricing.mv_card_price_spark;

CREATE MATERIALIZED VIEW pricing.mv_card_price_spark AS
WITH daily AS (
    SELECT
        ppd.card_version_id,
        ppd.price_date,
        COALESCE(AVG(ppd.list_avg_cents), AVG(ppd.sold_avg_cents)) / 100.0 AS avg_price
    FROM pricing.print_price_daily ppd
    JOIN pricing.price_source      ps ON ps.source_id = ppd.source_id
    WHERE ppd.transaction_type_id = 1
      AND ppd.condition_id        = 1
      AND ppd.language_id         = 1
      AND ppd.finish_id           = 1
      AND ps.currency_code        = 'USD'   -- US-market composite; keep EUR (cardmarket) out
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

-- Unique index — required for REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX idx_mv_card_price_spark_cv
    ON pricing.mv_card_price_spark (card_version_id);

-- Reissue read grants dropped along with the view
GRANT SELECT ON pricing.mv_card_price_spark
    TO app_celery, app_rw, app_admin, app_ro;

COMMIT;
