-- =============================================================================
-- public_schema_leak_check.sql
--
-- Purpose  : Confirms that the Scryfall pipeline (and the wider codebase) has
--            not leaked any objects into the `public` schema. Checks tables,
--            views, sequences, functions, and search_path configuration that
--            could cause unqualified queries to silently resolve to `public`.
--
-- How to run:
--   psql -U <role> -d automana -f public_schema_leak_check.sql
--
-- Expected frequency : After any schema migration or after suspicious
--                      pipeline failures; recommended weekly in CI.
--
-- Interpretation:
--   severity='error' — a card_catalog-domain object was found in public;
--                      this means queries using the pipeline's stored
--                      procedure could silently read stale public data.
--   severity='warn'  — non-extension, non-default object in public; may be
--                      a leftover from a developer session.
--   severity='info'  — search_path or role config for review; not an
--                      actionable finding by itself.
--
-- Output shape (all blocks):
--   check_name TEXT, severity TEXT, row_count BIGINT, details JSONB
--
-- Extension-owned objects:
--   pgvector (vector type, operators) and timescaledb both install objects
--   into public. These are identified via pg_depend and excluded from the
--   "non-default public objects" check.
-- =============================================================================

WITH

-- ---------------------------------------------------------------------------
-- 0. Helper: extension-owned object OIDs in public.
--    We exclude these from the "unexpected public objects" checks so that
--    pgvector and timescaledb noise doesn't drown out real findings.
-- ---------------------------------------------------------------------------
extension_owned_oids AS (
    SELECT
        d.objid
    FROM pg_depend d
    JOIN pg_extension e ON e.oid = d.refobjid
    WHERE d.deptype = 'e'
      AND d.classid = 'pg_class'::regclass
),

-- ---------------------------------------------------------------------------
-- CHECK 01: Card-catalog-domain tables in public.
--           Any table in public whose name matches a known card_catalog table
--           name means the pipeline wrote to the wrong schema.
--           Non-zero = critical data routing error; error.
-- ---------------------------------------------------------------------------
chk_01_card_catalog_tables_in_public AS (
    SELECT
        'card-catalog-tables-in-public'::TEXT             AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT t.table_name, t.table_type
                FROM information_schema.tables t
                WHERE t.table_schema = 'public'
                  AND t.table_name = ANY(ARRAY[
                      'sets', 'card_version', 'unique_cards_ref', 'illustrations',
                      'artists_ref', 'card_faces', 'face_illustration',
                      'card_version_illustration', 'illustration_artist',
                      'card_external_identifier', 'card_identifier_ref',
                      'scryfall_migration', 'legalities', 'card_types',
                      'card_keyword', 'color_produced', 'card_color_identity',
                      'rarities_ref', 'border_color_ref', 'frames_ref',
                      'layouts_ref', 'keywords_ref', 'formats_ref',
                      'legal_status_ref', 'icon_set', 'icon_query_ref',
                      'set_type_list_ref', 'language_ref', 'card_stats_ref',
                      'card_version_stats', 'games_ref', 'games_card_version',
                      'promo_types_ref', 'promo_card', 'card_games_ref'
                  ])
                ORDER BY t.table_name
                LIMIT 5
            ) s
        ) AS details
    FROM information_schema.tables t
    WHERE t.table_schema = 'public'
      AND t.table_name = ANY(ARRAY[
          'sets', 'card_version', 'unique_cards_ref', 'illustrations',
          'artists_ref', 'card_faces', 'face_illustration',
          'card_version_illustration', 'illustration_artist',
          'card_external_identifier', 'card_identifier_ref',
          'scryfall_migration', 'legalities', 'card_types',
          'card_keyword', 'color_produced', 'card_color_identity',
          'rarities_ref', 'border_color_ref', 'frames_ref',
          'layouts_ref', 'keywords_ref', 'formats_ref',
          'legal_status_ref', 'icon_set', 'icon_query_ref',
          'set_type_list_ref', 'language_ref', 'card_stats_ref',
          'card_version_stats', 'games_ref', 'games_card_version',
          'promo_types_ref', 'promo_card', 'card_games_ref'
      ])
),

-- ---------------------------------------------------------------------------
-- CHECK 02: Any non-extension-owned tables in public.
--           Extension-owned objects (pgvector, timescaledb) are excluded.
--           Non-zero = unexpected user table in public; warn.
-- ---------------------------------------------------------------------------
chk_02_unexpected_tables_in_public AS (
    SELECT
        'unexpected-tables-in-public'::TEXT               AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT c.relname AS object_name, c.relkind AS object_type,
                       pg_get_userbyid(c.relowner) AS owner
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relkind IN ('r', 'p')   -- ordinary + partitioned tables
                  AND c.oid NOT IN (SELECT objid FROM extension_owned_oids)
                ORDER BY c.relname
                LIMIT 5
            ) s
        ) AS details
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'p')
      AND c.oid NOT IN (SELECT objid FROM extension_owned_oids)
),

-- ---------------------------------------------------------------------------
-- CHECK 03: Views in public (non-extension-owned).
--           Any view in public could shadow schema-qualified queries; warn.
-- ---------------------------------------------------------------------------
chk_03_views_in_public AS (
    SELECT
        'views-in-public'::TEXT                           AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT c.relname AS view_name, pg_get_userbyid(c.relowner) AS owner
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relkind IN ('v', 'm')   -- views + materialized views
                  AND c.oid NOT IN (SELECT objid FROM extension_owned_oids)
                ORDER BY c.relname
                LIMIT 5
            ) s
        ) AS details
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind IN ('v', 'm')
      AND c.oid NOT IN (SELECT objid FROM extension_owned_oids)
),

-- ---------------------------------------------------------------------------
-- CHECK 04: Sequences in public (non-extension-owned).
--           Sequences leak when tables are created without schema qualification.
-- ---------------------------------------------------------------------------
chk_04_sequences_in_public AS (
    SELECT
        'sequences-in-public'::TEXT                       AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT c.relname AS sequence_name, pg_get_userbyid(c.relowner) AS owner
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relkind = 'S'
                  AND c.oid NOT IN (SELECT objid FROM extension_owned_oids)
                ORDER BY c.relname
                LIMIT 5
            ) s
        ) AS details
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind = 'S'
      AND c.oid NOT IN (SELECT objid FROM extension_owned_oids)
),

-- ---------------------------------------------------------------------------
-- CHECK 05: Functions / procedures in public (non-extension-owned).
--           A function in public with the same name as a card_catalog function
--           could shadow the intended target under certain search_paths; warn.
-- ---------------------------------------------------------------------------
chk_05_functions_in_public AS (
    SELECT
        'functions-in-public'::TEXT                       AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT p.proname AS function_name,
                       pg_get_userbyid(p.proowner) AS owner,
                       CASE p.prokind WHEN 'f' THEN 'function' WHEN 'p' THEN 'procedure'
                                      WHEN 'a' THEN 'aggregate' ELSE 'other' END AS kind
                FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'public'
                  AND p.oid NOT IN (SELECT objid FROM extension_owned_oids)
                ORDER BY p.proname
                LIMIT 5
            ) s
        ) AS details
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public'
      AND p.oid NOT IN (SELECT objid FROM extension_owned_oids)
),

-- ---------------------------------------------------------------------------
-- CHECK 06: search_path hygiene — current session.
--           Surfaces the active search_path so a reviewer can confirm
--           `public` is not first and `card_catalog` / `ops` are included.
--           Always severity='info'; review manually.
-- ---------------------------------------------------------------------------
chk_06_session_search_path AS (
    SELECT
        'session-search-path'::TEXT                       AS check_name,
        1::BIGINT                                         AS bad_count,
        jsonb_build_object(
            'search_path', current_setting('search_path'),
            'current_user', current_user,
            'session_user', session_user
        )                                                 AS details
),

-- ---------------------------------------------------------------------------
-- CHECK 07: Role-level search_path configuration.
--           Any role with a search_path that starts with `public` or lacks
--           `$user` puts unqualified queries at risk of hitting public first.
--           Returns roles that have an explicit search_path rolconfig entry.
-- ---------------------------------------------------------------------------
chk_07_role_search_path_config AS (
    SELECT
        'role-search-path-config'::TEXT                   AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT
                    r.rolname,
                    elem                                  AS search_path_setting
                FROM pg_roles r,
                     LATERAL unnest(r.rolconfig) AS elem
                WHERE elem ILIKE 'search_path%'
                ORDER BY r.rolname
                LIMIT 5
            ) s
        ) AS details
    FROM pg_roles r,
         LATERAL unnest(r.rolconfig) AS elem
    WHERE elem ILIKE 'search_path%'
),

-- ---------------------------------------------------------------------------
-- CHECK 08: Functions / procedures in card_catalog or ops schemas whose body
--           explicitly references `public.` (hardcoded schema prefix).
--           Such references bypass search_path and may indicate a development
--           artifact or copy-paste error; warn.
-- ---------------------------------------------------------------------------
chk_08_proc_body_references_public AS (
    SELECT
        'proc-body-references-public'::TEXT               AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT
                    n.nspname  AS schema_name,
                    p.proname  AS function_name,
                    -- Show a snippet of the match rather than the full body
                    substring(p.prosrc FROM position('public.' IN p.prosrc) - 20
                                       FOR 60)            AS body_snippet
                FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname IN ('card_catalog', 'ops')
                  AND p.prosrc ~ 'public\.'
                ORDER BY n.nspname, p.proname
                LIMIT 5
            ) s
        ) AS details
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname IN ('card_catalog', 'ops')
      AND p.prosrc ~ 'public\.'
)

-- ---------------------------------------------------------------------------
-- Final UNION — standard shape.
-- ---------------------------------------------------------------------------
SELECT
    check_name,
    CASE
        WHEN check_name = 'card-catalog-tables-in-public'
             THEN CASE WHEN bad_count > 0 THEN 'error' ELSE 'info' END
        WHEN check_name IN ('session-search-path', 'role-search-path-config')
             THEN 'info'
        ELSE CASE WHEN bad_count > 0 THEN 'warn' ELSE 'info' END
    END                                                   AS severity,
    bad_count                                             AS row_count,
    COALESCE(details, '[]'::jsonb)                        AS details
FROM (
    SELECT check_name, bad_count, details FROM chk_01_card_catalog_tables_in_public
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_02_unexpected_tables_in_public
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_03_views_in_public
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_04_sequences_in_public
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_05_functions_in_public
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_06_session_search_path
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_07_role_search_path_config
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_08_proc_body_references_public
) all_checks
ORDER BY
    CASE severity WHEN 'error' THEN 1 WHEN 'warn' THEN 2 ELSE 3 END,
    check_name
;
