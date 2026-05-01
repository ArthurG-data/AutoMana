-- migration_19: add SECURITY DEFINER + pinned search_path to refresh_card_search_views()
-- and grant EXECUTE to the roles that call it.
--
-- Why: app_celery only has USAGE on card_catalog; REFRESH MATERIALIZED VIEW CONCURRENTLY
-- requires ownership of the view. SECURITY DEFINER lets the procedure run as its owner
-- (db_owner) regardless of the caller's privileges. The pinned search_path prevents
-- search_path injection for future edits to this procedure.

CREATE OR REPLACE PROCEDURE card_catalog.refresh_card_search_views()
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = card_catalog, pg_catalog
AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY card_catalog.v_card_versions_complete;
    REFRESH MATERIALIZED VIEW CONCURRENTLY card_catalog.v_card_name_suggest;
END;
$$;

-- GRANT EXECUTE is required even with SECURITY DEFINER: the caller must still have
-- permission to invoke the procedure. ALL FUNCTIONS (used in apply_schema_grants.sql)
-- does not cover procedures in PostgreSQL 11+.
GRANT EXECUTE ON PROCEDURE card_catalog.refresh_card_search_views() TO app_celery, app_rw, app_admin;
