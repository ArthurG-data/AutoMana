update_bulk_scryfall_data_sql = """
WITH payload AS (
  SELECT %s::jsonb AS j
),
items AS (
  SELECT
    d->>'id'               AS external_id,
    d->>'type'             AS external_type,
    d->>'uri'              AS api_uri,
    d->>'download_uri'     AS download_uri,
    d->>'content_type'     AS content_type,
    d->>'content_encoding' AS content_encoding,
    (d->>'updated_at')::timestamptz AS updated_at_source,
    (d->>'size')::bigint   AS bytes,
    d                      AS metadata,
    d->>'name'             AS name,
    d->>'description'      AS description
  FROM payload p
  CROSS JOIN LATERAL jsonb_array_elements(p.j->'data') AS d
),
upsert_resources AS (
  INSERT INTO ops.resources (
    source_id, external_type, external_id, canonical_key, name, description,
    api_uri, web_uri, metadata, updated_at_source
  )
  SELECT
    %s::bigint AS source_id,
    i.external_type,
    i.external_id,
    NULL,
    i.name,
    i.description,
    i.api_uri,
    NULL,
    i.metadata,
    i.updated_at_source
  FROM items i
  ON CONFLICT ON CONSTRAINT ops_resources_source_type_external_key_uk  -- see section 2
  DO UPDATE SET
    name              = EXCLUDED.name,
    description       = EXCLUDED.description,
    api_uri           = EXCLUDED.api_uri,
    web_uri           = EXCLUDED.web_uri,
    metadata          = EXCLUDED.metadata,
    updated_at_source = EXCLUDED.updated_at_source
  RETURNING id AS resource_id, external_id, external_type
),
ins_versions AS (
  INSERT INTO ops.resource_versions (
    resource_id, download_uri, content_type, content_encoding, bytes,
    last_modified, status, etag, sha256
  )
  SELECT
    ur.resource_id,
    i.download_uri,
    i.content_type,
    i.content_encoding,
    i.bytes,
    i.updated_at_source,
    'downloaded',
    NULL::text,
    NULL::text
  FROM upsert_resources ur
  JOIN items i
    ON i.external_id = ur.external_id
   AND i.external_type = ur.external_type
  WHERE NOT EXISTS (
    SELECT 1
    FROM ops.resource_versions v
    WHERE v.resource_id   = ur.resource_id
      AND v.download_uri  = i.download_uri
      AND v.last_modified = i.updated_at_source
  )
  RETURNING 1
)
SELECT
  (SELECT COUNT(*) FROM upsert_resources) AS resources_upserted,
  (SELECT COUNT(*) FROM ins_versions)     AS versions_inserted;
"""