-- =============================================================================
-- tier_health_check.sql
--
-- Purpose  : Health checks for pricing tier 2/3 (print_price_daily/weekly)
--            data integrity and archival status. Reports:
--            - Tier 1 → Tier 2 synchronization
--            - Archival readiness (rows >5 years old)
--            - Tier 3 population status
--            - Watermark staleness
--
-- How to run:
--   psql -U app_admin -d automana -f tier_health_check.sql
--
-- Output: Health report showing tier data integrity and archival status
-- =============================================================================

\pset border 1
\pset format aligned

-- Tier Data Summary
SELECT '╔════════════════════════════════════════════════════════════════╗' as report;
SELECT '║                  TIER HEALTH CHECK REPORT                      ║' as report;
SELECT '╚════════════════════════════════════════════════════════════════╝' as report;

\echo ''
\echo '1. DATA SYNCHRONIZATION (Tier 1 ↔ Tier 2)'
\echo '─────────────────────────────────────────'

SELECT
  tier,
  rows,
  min_date,
  max_date,
  CASE
    WHEN tier = 'Tier 1' AND rows = (SELECT COUNT(*) FROM pricing.print_price_daily) THEN '✓ Synced'
    WHEN tier = 'Tier 2' AND rows = (SELECT COUNT(*) FROM pricing.price_observation) THEN '✓ Synced'
    ELSE 'Check'
  END as status
FROM (
  SELECT 'Tier 1 (price_observation)' as tier, COUNT(*) as rows, MIN(ts_date)::text as min_date, MAX(ts_date)::text as max_date FROM pricing.price_observation
  UNION ALL
  SELECT 'Tier 2 (print_price_daily)', COUNT(*), MIN(price_date)::text, MAX(price_date)::text FROM pricing.print_price_daily
) tiers
ORDER BY tier;

-- Sync status detail
SELECT
  CASE
    WHEN (SELECT COUNT(*) FROM pricing.price_observation) = (SELECT COUNT(*) FROM pricing.print_price_daily)
    THEN '✓ PASS: Tier 1 and Tier 2 row counts match'
    ELSE '✗ FAIL: Tier 1 and Tier 2 row count mismatch!'
  END as sync_status;

\echo ''
\echo '2. ARCHIVAL STATUS (Rows eligible for Tier 3)'
\echo '──────────────────────────────────────────────'

SELECT
  COUNT(*) as archivable_rows,
  ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM pricing.print_price_daily), 1) as pct_of_tier2,
  (CURRENT_DATE - INTERVAL '5 years')::text as cutoff_date,
  CASE
    WHEN COUNT(*) > 0 THEN '⚠ Ready: Run archive_to_weekly()'
    ELSE '✓ No old data to archive'
  END as status
FROM pricing.print_price_daily
WHERE price_date < CURRENT_DATE - INTERVAL '5 years';

\echo ''
\echo '3. TIER 3 POPULATION STATUS'
\echo '─────────────────────────────'

SELECT
  COUNT(*) as tier3_rows,
  MIN(price_week)::text as oldest_week,
  MAX(price_week)::text as newest_week,
  CASE
    WHEN COUNT(*) = 0 AND (SELECT COUNT(*) FROM pricing.print_price_daily WHERE price_date < CURRENT_DATE - INTERVAL '5 years') > 0
    THEN '⚠ Empty - awaiting archive_to_weekly() execution'
    WHEN COUNT(*) = 0
    THEN '✓ Empty - but no data older than 5 years to archive'
    ELSE '✓ Populated: ' || COUNT(*)::text || ' rows'
  END as status
FROM pricing.print_price_weekly;

\echo ''
\echo '4. WATERMARK STATUS (Refresh Progress)'
\echo '──────────────────────────────────────'

SELECT
  tier_name,
  last_processed_date,
  (CURRENT_DATE - last_processed_date) as days_behind,
  CASE
    WHEN tier_name = 'daily' AND last_processed_date >= CURRENT_DATE - 1 THEN '✓ Fresh'
    WHEN tier_name = 'daily' AND last_processed_date >= CURRENT_DATE - 2 THEN '⚠ Slightly stale'
    WHEN tier_name = 'daily' THEN '✗ Stale (>2 days)'
    WHEN tier_name = 'weekly' AND last_processed_date = '1970-01-01' THEN '⚠ Never run'
    ELSE '✓ OK'
  END as freshness
FROM pricing.tier_watermark
ORDER BY tier_name;

\echo ''
\echo '5. SOURCE & CARD COVERAGE'
\echo '──────────────────────────'

SELECT
  metric,
  count_value::text as value
FROM (
  SELECT 'Distinct Sources in Tier 1' as metric, COUNT(DISTINCT source_id)::bigint as count_value FROM pricing.price_observation
  UNION ALL
  SELECT 'Distinct Sources in Tier 2', COUNT(DISTINCT source_id) FROM pricing.print_price_daily
  UNION ALL
  SELECT 'Distinct Cards in Tier 1', COUNT(DISTINCT card_version_id) FROM pricing.price_observation
  UNION ALL
  SELECT 'Distinct Cards in Tier 2', COUNT(DISTINCT card_version_id) FROM pricing.print_price_daily
) metrics
ORDER BY metric;

\echo ''
\echo '═══════════════════════════════════════════════════════════════════'
\echo 'Next Steps:'
\echo '─────────'
\echo '1. If Tier 2 has archivable_rows > 0, run: CALL pricing.archive_to_weekly();'
\echo '2. Monitor watermark staleness (daily should be < 2 days behind)'
\echo '3. See docs/MTGSTOCK_PIPELINE.md for operations details'
\echo '═══════════════════════════════════════════════════════════════════'
