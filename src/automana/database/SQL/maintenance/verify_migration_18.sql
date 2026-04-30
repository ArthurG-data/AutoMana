-- verify_migration_18.sql
-- Run BEFORE migration to confirm failures, AFTER to confirm passes.
-- Every check outputs: check_name, status ('pass'/'fail'), detail

SELECT 'print_price_daily_exists' AS check_name,
       CASE WHEN EXISTS (
           SELECT 1 FROM pg_class c
           JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = 'pricing' AND c.relname = 'print_price_daily'
       ) THEN 'pass' ELSE 'fail' END AS status,
       'table must exist' AS detail

UNION ALL

SELECT 'print_price_daily_has_source_id',
       CASE WHEN EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'pricing'
             AND table_name   = 'print_price_daily'
             AND column_name  = 'source_id'
       ) THEN 'pass' ELSE 'fail' END,
       'source_id column required (old stub lacked it)'

UNION ALL

SELECT 'print_price_daily_no_p25',
       CASE WHEN NOT EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'pricing'
             AND table_name   = 'print_price_daily'
             AND column_name  = 'p25_price'
       ) THEN 'pass' ELSE 'fail' END,
       'p25_price must NOT exist (dropped)'

UNION ALL

SELECT 'print_price_daily_is_hypertable',
       CASE WHEN EXISTS (
           SELECT 1 FROM timescaledb_information.hypertables
           WHERE hypertable_schema = 'pricing'
             AND hypertable_name   = 'print_price_daily'
       ) THEN 'pass' ELSE 'fail' END,
       'must be a TimescaleDB hypertable'

UNION ALL

SELECT 'print_price_weekly_exists',
       CASE WHEN EXISTS (
           SELECT 1 FROM pg_class c
           JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = 'pricing' AND c.relname = 'print_price_weekly'
       ) THEN 'pass' ELSE 'fail' END,
       'table must exist'

UNION ALL

SELECT 'print_price_weekly_has_n_days',
       CASE WHEN EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'pricing'
             AND table_name   = 'print_price_weekly'
             AND column_name  = 'n_days'
       ) THEN 'pass' ELSE 'fail' END,
       'n_days column required'

UNION ALL

SELECT 'print_price_latest_exists',
       CASE WHEN EXISTS (
           SELECT 1 FROM pg_class c
           JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = 'pricing' AND c.relname = 'print_price_latest'
       ) THEN 'pass' ELSE 'fail' END,
       'table must exist'

UNION ALL

SELECT 'tier_watermark_seeded',
       CASE WHEN (
           SELECT COUNT(*) FROM pricing.tier_watermark
           WHERE tier_name IN ('daily', 'weekly')
       ) = 2 THEN 'pass' ELSE 'fail' END,
       'must have 2 rows: daily + weekly'

UNION ALL

SELECT 'refresh_daily_prices_exists',
       CASE WHEN EXISTS (
           SELECT 1 FROM pg_proc p
           JOIN pg_namespace n ON n.oid = p.pronamespace
           WHERE n.nspname = 'pricing'
             AND p.proname = 'refresh_daily_prices'
       ) THEN 'pass' ELSE 'fail' END,
       'procedure must exist'

UNION ALL

SELECT 'archive_to_weekly_exists',
       CASE WHEN EXISTS (
           SELECT 1 FROM pg_proc p
           JOIN pg_namespace n ON n.oid = p.pronamespace
           WHERE n.nspname = 'pricing'
             AND p.proname = 'archive_to_weekly'
       ) THEN 'pass' ELSE 'fail' END,
       'procedure must exist'

ORDER BY check_name;
