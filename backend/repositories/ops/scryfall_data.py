update_bulk_scryfall_data_sql = """
WITH payload AS (
  SELECT $1::jsonb AS j
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
    $2::bigint AS source_id,
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
  ON CONFLICT (source_id, external_type,  external_id, canonical_key)
  DO UPDATE SET
    name              = EXCLUDED.name,
    description       = EXCLUDED.description,
    api_uri           = EXCLUDED.api_uri,
    web_uri           = EXCLUDED.web_uri,
    metadata          = EXCLUDED.metadata,
    updated_at_source = EXCLUDED.updated_at_source
  WHERE ops.resources.updated_at_source IS NULL
     OR EXCLUDED.updated_at_source > ops.resources.updated_at_source
  RETURNING id AS resource_id, external_id, external_type
),
changed AS (
  SELECT
    ur.resource_id,
    ur.external_id,
    ur.external_type,
    i.download_uri,
    i.updated_at_source,
    i.bytes
  FROM upsert_resources ur
  JOIN items i
    ON i.external_id = ur.external_id
   AND i.external_type = ur.external_type
),
ins_versions AS (
  INSERT INTO ops.resource_versions (
    resource_id,
    download_uri,
    content_type,
    content_encoding,
    bytes,
    last_modified,
    status,
    etag,
    sha256
  )
  SELECT
    c.resource_id,
    c.download_uri,
    i.content_type,
    i.content_encoding,
    c.bytes,
    c.updated_at_source,
    'downloaded',
    NULL::text,
    NULL::text
  FROM changed c
  JOIN items i
    ON i.external_id = c.external_id
   AND i.external_type = c.external_type
  WHERE NOT EXISTS (
    SELECT 1
    FROM ops.resource_versions v
    WHERE v.resource_id   = c.resource_id
      AND v.download_uri  = c.download_uri
      AND v.last_modified = c.updated_at_source
  )
  RETURNING 1
)
SELECT
  (SELECT COUNT(*) FROM upsert_resources) AS resources_upserted,
  (SELECT COUNT(*) FROM ins_versions)     AS versions_inserted,
  COALESCE(
    (SELECT jsonb_agg(jsonb_build_object(
        'type', external_type,
        'external_id', external_id,
        'download_uri', download_uri,
        'updated_at', updated_at_source
    ) ORDER BY external_type) FROM changed),
    '[]'::jsonb
  ) AS changed_entries;
"""