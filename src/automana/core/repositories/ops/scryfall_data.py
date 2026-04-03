update_bulk_scryfall_data_sql = """
WITH
-- ── 1. Parse manifest items from the JSON array passed as $1 ─────────────────
items AS (
  SELECT
    d->>'id'               AS external_id,
    d->>'type'             AS external_type,
    d->>'uri'              AS api_uri,
    d->>'name'             AS name,
    d->>'description'      AS description,
    d->>'download_uri'     AS download_uri,
    d->>'content_type'     AS content_type,
    d->>'content_encoding' AS content_encoding,
    (d->>'updated_at')::timestamptz AS last_modified,
    (d->>'size')::bigint   AS bytes,
    d                      AS metadata
  FROM jsonb_array_elements($1::jsonb) AS d
),

-- ── 2. Resolve source_id: from ingestion run when provided, else by name ─────
--      Fallback allows standalone testing without a prior start_pipeline call.
run_source AS (
  SELECT src_id AS source_id FROM (
    SELECT COALESCE(
      (SELECT source_id FROM ops.ingestion_runs WHERE id = $2::bigint),
      (SELECT id        FROM ops.sources          WHERE name = 'scryfall')
    ) AS src_id
  ) t WHERE src_id IS NOT NULL
),

-- ── 3. Upsert one ops.resources row per bulk file type ────────────────────────
--      Uses the partial unique index ux_resources_no_canonical_key.
--      Always RETURNING the resource id so step 4 can join to it directly —
--      CTEs share the same snapshot and cannot read rows inserted by a
--      sibling CTE, so we must carry the id through RETURNING instead of
--      re-reading ops.resources.
upsert_resources AS (
  INSERT INTO ops.resources (
    source_id, external_type, external_id, canonical_key,
    name, description, api_uri, metadata, updated_at_source
  )
  SELECT
    rs.source_id,
    i.external_type,
    i.external_id,
    NULL,
    i.name,
    i.description,
    i.api_uri,
    i.metadata,
    i.last_modified
  FROM items i, run_source rs
  ON CONFLICT (source_id, external_type, external_id)
    WHERE canonical_key IS NULL
  DO UPDATE SET
    api_uri           = CASE WHEN EXCLUDED.updated_at_source > ops.resources.updated_at_source
                             THEN EXCLUDED.api_uri    ELSE ops.resources.api_uri    END,
    metadata          = CASE WHEN EXCLUDED.updated_at_source > ops.resources.updated_at_source
                             THEN EXCLUDED.metadata   ELSE ops.resources.metadata   END,
    updated_at_source = GREATEST(EXCLUDED.updated_at_source, ops.resources.updated_at_source)
  RETURNING id AS resource_id, external_type, external_id
),

-- ── 4. Join items to the upserted resource rows to get resource_id ────────────
resolved AS (
  SELECT
    ur.resource_id,
    i.external_id,
    i.external_type,
    i.download_uri,
    i.content_type,
    i.content_encoding,
    i.last_modified,
    i.bytes
  FROM items i
  JOIN upsert_resources ur
    ON  ur.external_type = i.external_type
    AND ur.external_id   = i.external_id
),

-- ── 5. Keep only items with no existing version for this (resource, uri, timestamp) ──
changed AS (
  SELECT * FROM resolved r
  WHERE NOT EXISTS (
    SELECT 1 FROM ops.resource_versions v
    WHERE v.resource_id  = r.resource_id
      AND v.download_uri = r.download_uri
      AND v.last_modified IS NOT DISTINCT FROM r.last_modified
  )
),

-- ── 6. Insert a new resource_version row for each changed item ────────────────
ins_versions AS (
  INSERT INTO ops.resource_versions (
    resource_id, download_uri, content_type, content_encoding,
    bytes, last_modified, status
  )
  SELECT
    resource_id, download_uri, content_type, content_encoding,
    bytes, last_modified, 'downloaded'
  FROM changed
  ON CONFLICT (resource_id, download_uri, last_modified) DO NOTHING
  RETURNING resource_id, download_uri, last_modified
)

-- ── 7. Return summary + list of new download URIs for the pipeline ────────────
SELECT
  (SELECT COUNT(*) FROM items)             AS items_seen,
  (SELECT COUNT(*) FROM upsert_resources)  AS resources_upserted,
  (SELECT COUNT(*) FROM ins_versions)      AS versions_inserted,
  COALESCE(
    (SELECT jsonb_agg(
        jsonb_build_object(
          'resource_id',   iv.resource_id,
          'download_uri',  iv.download_uri,
          'last_modified', iv.last_modified,
          'external_type', r.external_type
        ) ORDER BY iv.resource_id
      )
     FROM ins_versions iv
     JOIN ops.resources r ON r.id = iv.resource_id),
    '[]'::jsonb
  ) AS changed;
"""
