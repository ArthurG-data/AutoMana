from celery_main_app import celery_app
from connection import get_connection
from http_utils import get
import pathlib, logging
from sqlalchemy import text



@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def update_scryfall_bulk_uris(self):
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
    save_path = "G:/automana" / pathlib.Path(dest.get("path")) #HARDCAODE FOR THE MOMENT

    logging.info(f"Downloading manifest from {api_uri} -> {save_path}")
    # ensure directory exists
    resp = get(api_uri)        # your http.get wrapper (requests)
    resp.raise_for_status()
    pathlib.Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(save_path).write_text(resp.text)

    logging.info(f"Wrote manifest to {save_path} (bytes={len(resp.content)})")

    return {"resource_id": row["id"], "path": str(save_path), "bytes": len(resp.content)}

@celery_app.task
def download_scryfall_data(url, save_path):
    pass

def update_scryfall_database():
    pass

   