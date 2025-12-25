from asyncio.log import logger
import sys
import os
import tempfile
from main import celery_app
from connection import get_connection
from http_utils import get
import pathlib, logging
from sqlalchemy import text

'''
@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def download_scryfall_bulk_uris(self):
    #get bulk data uris from database
    with get_connection() as connection:
        SQL = """
        SELECT r.*
        FROM ops.resources r
        JOIN ops.sources s ON s.kind = 'http' and s.name = 'scryfall' AND r.external_type = 'bulk_data'
        ORDER BY s.updated_at DESC
        LIMIT 1;
        """
        row = connection.execute(text(SQL)).mappings().first()
    if not row:
        raise RuntimeError("No ops.resources row found for scryfall bulk-data manifest")

    api_uri = row["api_uri"]                     # ex: https://api.scryfall.com/bulk-data
    meta = row.get("metadata") or {}
    dest = (meta.get("destination") or {})
    save_path = pathlib.Path("G:/automana") / pathlib.Path(dest.get("path")) #HARDCAODE FOR THE MOMENT

    logging.info(f"Downloading manifest from {api_uri} -> {save_path}")
    # ensure directory exists
    resp = get(api_uri)        # your http.get wrapper (requests)
    resp.raise_for_status()
    pathlib.Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(save_path).write_text(resp.text)

    logging.info(f"Wrote manifest to {save_path} (bytes={len(resp.content)})")

    #call task to process the manifest
    process_scryfall_bulk_uris.s({"source_id": row["source_id"], "path": str(save_path), "bytes": len(resp.content)}).apply_async()


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def process_scryfall_bulk_uris(self, result):
    source_id = result["source_id"]
    path = result["path"]
    bytes = result["bytes"]

    logging.info(f"Processing scryfall bulk data manifest {path} (bytes={bytes})")

    # read the manifest file
    manifest = pathlib.Path(path).read_text()
    import json
    manifest = json.loads(manifest)

    with get_connection() as connection:
        trans = connection.begin()
        try:
            SQL = """
            WITH payload AS (
                SELECT CAST(:manifest AS jsonb) AS j
                ),
                items AS (
                SELECT
                    d->>'id'              AS external_id,
                    d->>'type'            AS external_type,
                    d->>'uri'             AS api_uri,
                    d->>'download_uri'    AS download_uri,
                    d->>'content_type'    AS content_type,
                    d->>'content_encoding'AS content_encoding,
                    (d->>'updated_at')::timestamptz AS updated_at_source,
                    (d->>'size')::bigint  AS bytes,
                    d                     AS metadata,
                    d->>'name'            AS name,
                    d->>'description'     AS description
                FROM payload p
                CROSS JOIN LATERAL jsonb_array_elements(p.j->'data') AS d
                ),
                upsert_resources AS (
                INSERT INTO ops.resources (
                    source_id,
                    external_type,
                    external_id,
                    canonical_key,
                    name,
                    description,
                    api_uri,
                    web_uri,
                    metadata,
                    updated_at_source
                )
                SELECT
                    CAST(:source_id AS bigint)                  AS source_id,
                    i.external_type,
                    i.external_id,
                    NULL                        AS canonical_key,
                    i.name,
                    i.description,
                    i.api_uri,
                    NULL                        AS web_uri,
                    i.metadata,
                    i.updated_at_source
                FROM items i
                ON CONFLICT (source_id, external_type, COALESCE(external_id, canonical_key))
                DO UPDATE
                    SET name              = EXCLUDED.name,
                        description       = EXCLUDED.description,
                        api_uri           = EXCLUDED.api_uri,
                        web_uri           = EXCLUDED.web_uri,
                        metadata          = EXCLUDED.metadata,
                        updated_at_source = EXCLUDED.updated_at_source
                RETURNING id AS resource_id, external_id, external_type
                ),
                ins_versions AS (
                INSERT INTO ops.resource_versions (
                    resource_id,
                    download_uri,
                    content_type,
                    content_encoding,
                    bytes,
                    last_modified,
                    status,      -- we only know metadata here; mark as downloaded
                    etag,
                    sha256
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
                -- avoid duplicate version rows for the same file snapshot
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
            result = connection.execute(
                text(SQL), 
                {"manifest": json.dumps(manifest),  # or just manifest if your driver auto-adapts
                    "source_id": source_id,
                }
                )
            counts = result.mappings().first()
            trans.commit()
            logging.info(f"Upserted {counts['resources_upserted']} resources, inserted {counts['versions_inserted']} new versions")
        except Exception as e:
            trans.rollback()
            logging.error(f"Error processing scryfall bulk URIs: {e}")
            raise
        return {
    "source_id": source_id,
    "resources_upserted": counts['resources_upserted'],   # First column
    "versions_inserted": counts['versions_inserted']      # Second column



}
   
import os
from datetime import time

@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def download_scryfall_data(self, external_type, save_path):
    #check if folder exists
    save_path = pathlib.Path(save_path)

    save_path.parent.mkdir(parents=True, exist_ok=True)
    
    #check in the db if the new file has been updated sinc last download
    SQL = """
    SELECT 
            r.id,
            r.external_id,
            r.name,
            rv.id as version_id,
            rv.download_uri,
            rv.content_type,
            rv.bytes as expected_bytes,
            rv.last_modified,
            -- Extract updated_at from JSON metadata
            (r.metadata->>'updated_at')::timestamptz AS metadata_updated_at,
            r.metadata->>'size' AS metadata_size,
            r.metadata->>'download_uri' AS metadata_download_uri
        FROM ops.resources r
        JOIN ops.resource_versions rv ON rv.resource_id = r.id
        JOIN ops.sources s ON s.id = r.source_id
        WHERE s.name = 'scryfall' 
        AND r.external_type = :external_type
        ORDER BY rv.last_modified DESC
        LIMIT 1;
    """
    with get_connection() as connection:
        row = connection.execute(text(SQL), {"external_type": external_type}).mappings().first()
        if not row:
            raise RuntimeError(f"No ops.resources row found for scryfall external_type={external_type}")
        
        metadata_updated_at = row['metadata_updated_at']
      
        download_uri = row['metadata_download_uri'] or row['download_uri']
        expected_bytes = int(row['metadata_size']) if row['metadata_size'] else row['expected_bytes']
        last_modified = row['last_modified']

        logging.info(f"Resource '{external_type}' updated at: {metadata_updated_at}")
        
        # Check if we need to download
        if  metadata_updated_at and last_modified and last_modified >= metadata_updated_at:
            if save_path.exists():
                logging.info(f"File {save_path} is up to date, skipping download")
                return {
                    "status": "skipped",
                    "reason": "file_up_to_date",
                    "local_path": str(save_path),
                    "metadata_updated_at": metadata_updated_at.isoformat()
                }
        
        # Download the file
        logging.info(f"Downloading {external_type} from {download_uri} to {save_path}")
        
        response = get(download_uri, stream=True)
        response.raise_for_status()

        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                logging.info(f"Downloaded chunk of size {len(chunk)}")
        actual_bytes = os.path.getsize(save_path)
        trans = connection.begin()
        try:
            # Update the version record
            SQL_update = """
            UPDATE ops.resource_versions
            SET 
                local_path = :local_path,
                bytes = :bytes,
                last_modified = NOW(),
                status = 'downloaded'
            WHERE id = :version_id
            """
            connection.execute(
                text(SQL_update),
                {
                    "local_path": str(save_path),
                    "bytes": actual_bytes,
                    "version_id": row['version_id']
                }
            )

            trans.commit()
        except Exception as e:
            trans.rollback()
            logging.error(f"Failed to update resource version: {e}")
            raise

        logging.info(f"✅ Downloaded {external_type}: {actual_bytes} bytes")
        
        return {
            "status": "downloaded",
            "external_type": external_type,
            "local_path": str(save_path),
            "bytes_downloaded": actual_bytes,
            "expected_bytes": expected_bytes,
            "metadata_updated_at": metadata_updated_at.isoformat() if metadata_updated_at else None
        }

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def stage_scryfall_set_data(self, file_path):
    """Process a large Scryfall sets JSON file and stage data into the database."""
    try:
        # Validate file type
        file_path = pathlib.Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File {file_path} does not exist")
        
        if not file_path.name.endswith('.json'):
            raise ValueError("Only JSON files are supported")
        
        # Check file size (optional limit)
        max_size =  1024 * 1024 * 1024  # 1GB default
        file_size = file_path.stat().st_size
        if file_size > max_size:
            raise ValueError(f"File too large. Maximum size: {max_size / 1024 / 1024:.1f}MB")
        logger.info(f"Processing file upload: {file_path.name}")

        from backend.repositories.card_catalog.set_repository import SetReferenceRepository
        from backend.request_handling.QueryExecutor import SQLAlchemyQueryExecutor
        
        with get_connection() as connection:
            #get a new connection everytime a failure happends
            try:
                # Create query executor and repository
                query_executor = SQLAlchemyQueryExecutor()
                set_repository = SetReferenceRepository(connection, query_executor)
                
                # Import the service function directly
                # You'll need to adjust this import based on your actual service structure
                from backend.new_services.card_catalog.set_service import process_large_sets_json 

                result = process_large_sets_json(
                        set_repository=set_repository,
                        file_path=str(file_path)
                    )

                logging.info(f"✅ Successfully processed file: {file_path}")
            
                return {
                    "status": "success",
                    "filename": file_path.name,
                    "file_path": str(file_path),
                    "file_size_mb": round(file_size / 1024 / 1024, 2),
                    "processing_stats": result.to_dict() if hasattr(result, 'to_dict') else result
                }
            except Exception as db_error:
                    # Log the specific database error
                    logging.error(f"Database error processing file '{file_path}': {str(db_error)}")
                    # Re-raise to trigger Celery retry
                    raise
        
    except FileNotFoundError as e:
        logging.error(f"File not found: {e}")
        raise
    except ValueError as e:
        logging.error(f"Validation error: {e}")
        raise
    except Exception as e:
        logging.error(f"Failed to process file '{file_path}': {str(e)}")
        raise
@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def stage_scryfall_card_data(self, file_path):
    """Process a large Scryfall cards JSON file and stage data into the database."""
    try:
        # Task implementation goes here
        file_path = pathlib.Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File {file_path} does not exist")
        
        if not file_path.name.endswith('.json'):
            raise ValueError("Only JSON files are supported")
        
        file_size = file_path.stat().st_size
        logging.info(f"Processing file upload: {file_path.name}")

        from backend.request_handling.QueryExecutor import SQLAlchemyQueryExecutor
        from backend.repositories.card_catalog.card_repository import CardReferenceRepository

        with get_connection() as connection:
            try:
                # Create query executor and repository
                query_executor = SQLAlchemyQueryExecutor()
                card_repository = CardReferenceRepository(connection, query_executor)
                
                # Import the service function directly
                # You'll need to adjust this import based on your actual service structure
                from backend.new_services.card_catalog.card_service import process_large_cards_json 

                result = process_large_cards_json(
                        card_repository=card_repository,
                        file_path=str(file_path)
                    )

                logging.info(f"✅ Successfully processed file: {file_path}")
            
                return {
                    "status": "success",
                    "filename": file_path.name,
                    "file_path": str(file_path),
                    "file_size_mb": round(file_size / 1024 / 1024, 2),
                    "processing_stats": result.to_dict() if hasattr(result, 'to_dict') else result
                }
            except Exception as db_error:
                logging.error(f"Database error processing file '{file_path}': {str(db_error)}")
                # Re-raise to trigger Celery retry
                raise
    except FileNotFoundError as e:
        logging.error(f"File not found: {e}")
        raise
    except ValueError as e:
        logging.error(f"Validation error: {e}")
        raise
    except Exception as e:
        logging.error(f"Failed to process file '{file_path}': {str(e)}")
        raise

@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def complete_scryfall_data_pipeline(self, source_id):
    pass
'''