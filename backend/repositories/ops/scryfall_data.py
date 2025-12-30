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
  RETURNING 1
),
resolved AS (
  SELECT
    r.id AS resource_id,
    i.external_id,
    i.external_type,
    i.download_uri,
    i.content_type,
    i.content_encoding,
    i.updated_at_source,
    i.bytes
  FROM items i
  JOIN ops.resources r
    ON r.source_id = $2::bigint
   AND r.external_type = i.external_type
   AND r.external_id = i.external_id
),
changed AS (
  SELECT
    r.resource_id,
    r.external_id,
    r.external_type,
    r.download_uri,
    r.content_type,
    r.content_encoding,
    r.updated_at_source,
    r.bytes
  FROM resolved r
  WHERE NOT EXISTS (
    SELECT 1
    FROM ops.resource_versions v
    WHERE v.resource_id   = r.resource_id
      AND v.download_uri  = r.download_uri
      AND v.last_modified = r.updated_at_source
  )
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
    res.resource_id,
    res.download_uri,
    res.content_type,
    res.content_encoding,
    res.bytes,
    res.updated_at_source,
    'downloaded',
    NULL::text,
    NULL::text
  FROM resolved res
  WHERE NOT EXISTS (
    SELECT 1
    FROM ops.resource_versions v
    WHERE v.resource_id   = res.resource_id
      AND v.download_uri  = res.download_uri
      AND v.last_modified IS NOT DISTINCT FROM res.updated_at_source
  )
  RETURNING resource_id, download_uri, last_modified
)

SELECT
  (SELECT COUNT(*) FROM items) AS items_seen,
  (SELECT COUNT(*) FROM upsert_resources) AS resources_upserted_or_updated,
  (SELECT COUNT(*) FROM ins_versions) AS versions_inserted,
  COALESCE(
    (SELECT jsonb_agg(jsonb_build_object(
      'resource_id', resource_id,
      'download_uri', download_uri,
      'last_modified', last_modified
    ) ORDER BY resource_id) FROM ins_versions),
    '[]'::jsonb
  ) AS new_versions;
  """