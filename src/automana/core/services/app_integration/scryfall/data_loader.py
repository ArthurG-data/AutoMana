import  logging,pathlib
from automana.core.repositories.app_integration.scryfall.ApiScryfall_repository import ScryfallAPIRepository
from automana.core.repositories.ops.ops_repository import OpsRepository
from automana.core.services.ops.pipeline_services import track_step
from automana.core.storage import StorageService

from datetime import datetime
from automana.core.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)


@ServiceRegistry.register("staging.scryfall.pipeline_finish"
                          , db_repositories=["ops"]
                          )
async def pipeline_finish(ops_repository: OpsRepository
                          , ingestion_run_id: int = None
                          , status: str = "success"
                          , notes: str | None = None):
    """Finish the Scryfall data ingestion pipeline by updating the run status in the Ops repository."""
    if ops_repository and ingestion_run_id:
        await ops_repository.finish_run(ingestion_run_id, status=status, notes=notes)
    return {"status": status}

@ServiceRegistry.register(path="staging.scryfall.start_pipeline",
                         db_repositories=["ops"])
async def scryfall_data_pipeline_start(ops_repository: OpsRepository
                                       ,pipeline_name: str="scryfall_daily"
                                       , source_name: str="scryfall"
                                       , celery_task_id: str = None
                                       , run_key: str=None) -> int:
    """ Start the Scryfall data ingestion pipeline by creating a new run in the Ops repository."""
    run_id = await ops_repository.start_run(pipeline_name
                                            , source_name=source_name
                                            , run_key=run_key or f"{pipeline_name}_{datetime.utcnow().strftime('%Y%m%d')}"
                                            , celery_task_id=celery_task_id
                                            , notes="Starting Scryfall data pipeline, scheduled daily ingestion.")
    logger.info("Scryfall pipeline run started", extra={"ingestion_run_id": run_id, "pipeline_name": pipeline_name})
    return {'ingestion_run_id': run_id}

#get bulk data uri
@ServiceRegistry.register("staging.scryfall.get_bulk_data_uri",
                         db_repositories=["ops"])
async def get_scryfall_bulk_data_uri(ops_repository: OpsRepository
                                      , ingestion_run_id: int = None
                                     ) -> str:
    """Retrieve Scryfall bulk data URIs from the database"""
    async with track_step(ops_repository, ingestion_run_id, "get_bulk_data_uri", error_code="no_bulk_uri"):
        bulk_uri = await ops_repository.get_bulk_data_uri()
        if not bulk_uri:
            raise ValueError("No bulk data URI found in the database.")
    return {"bulk_uri": bulk_uri}

#download bulk manifests
@ServiceRegistry.register("staging.scryfall.download_bulk_manifests",
                         api_repositories=["scryfall"]
                         , db_repositories=["ops"]
                         )
async def download_scryfall_bulk_manifests( ops_repository: OpsRepository
                                            ,scryfall_repository: ScryfallAPIRepository
                                           , bulk_uri: str
                                           , ingestion_run_id: int = None) -> str:
    """Download the Scryfall bulk data manifest"""
    async with track_step(ops_repository, ingestion_run_id, "download_bulk_manifests", error_code="download_failed"):
        manifests = await scryfall_repository.download_data_from_url(bulk_uri)
        if not manifests.get("data"):
            raise ValueError("Failed to download Scryfall bulk data manifest.")
    logger.info("Bulk manifest downloaded", extra={"ingestion_run_id": ingestion_run_id, "item_count": len(manifests["data"])})
    return {"items": manifests["data"]}

async def download_scryfall_from_url(repository: ScryfallAPIRepository
                                    , url: str
                                    , filename_out: str
                                  , storage_service: StorageService = None
):
    """Download Scryfall data from a given URL and save to specified path"""
    result = await repository.download_data_from_url(url)

    await storage_service.save_json(filename_out, result.get("data", {}))

    return {"file_path": filename_out}
    
        

async def stream_download_scryfall_json_from_uris(repository: ScryfallAPIRepository
                                            ,uri: str
                                           , storage_service: StorageService
                                           , ingestion_run_id: int = None):
    """Download Scryfall bulk data from given URIs and save to specified directory"""
    saved = []
    

    name = uri.split("/")[-1]  # ends with .json or .json.gz
    out = f"{str(ingestion_run_id or 'standalone')}_{datetime.utcnow().strftime('%Y%m%d')}_{name}"
    logger.info("Streaming bulk file", extra={"url": uri, "file": out, "ingestion_run_id": ingestion_run_id})
    async with repository.stream_download(str(uri).strip()) as chunks:
        async with storage_service.open_stream(out, "wb") as f:
            async for chunk in chunks:
                f.write(chunk)
    logger.info("Bulk file saved", extra={"file": out, "ingestion_run_id": ingestion_run_id})
    saved.append(str(out))

    return {"files_saved": saved}


@ServiceRegistry.register("staging.scryfall.update_data_uri_in_ops_repository",
                         db_repositories=["ops"]
                         )
async def update_data_uri_in_ops_repository(ops_repository: OpsRepository
                                            , items: dict
                                            , ingestion_run_id: int = None):
    """Update the bulk data URIs in the Ops repository,first update the source table with new uri if exists, then update resource_vertsions with the specified version to be used for the current run"""
    async with track_step(ops_repository, ingestion_run_id, "update_data_uri_in_ops_repository", error_code="update_failed"):
        result = await ops_repository.update_bulk_data_uri_return_new(items, ingestion_run_id)
    logger.info("Bulk data URIs updated in Ops repository", extra={"ingestion_run_id": ingestion_run_id, "updated_count": len(result.get("updated", [])), "updated": result.get("updated", [])})
    bulk_items_changed = result.get("changed", [])
    if not bulk_items_changed:
        logger.info("No changes in Scryfall bulk data URIs — skipping download", extra={"ingestion_run_id": ingestion_run_id})
    return {'uris_to_download': bulk_items_changed}

@ServiceRegistry.register("staging.scryfall.download_sets"
                          , api_repositories=["scryfall"]
                          , db_repositories=["ops"]
                          , storage_services=["scryfall"])
async def download_sets(
    scryfall_repository: ScryfallAPIRepository,
    ops_repository: OpsRepository,
    ingestion_run_id: int = None,
    storage_service: StorageService = None,
) -> dict:
    #TO DO :chekc if file exists before downloading, if exists, skip downloading and return the file path
    filename_out = f"scryfall_sets_{datetime.utcnow().strftime('%Y%m%d')}.json"
    if await storage_service.file_exists(filename_out):
        logger.info("Sets file already exists — skipping download", extra={"file": filename_out, "ingestion_run_id": ingestion_run_id})
    else:
        async with track_step(ops_repository, ingestion_run_id, "download_sets", error_code="download_failed"):
            await download_scryfall_from_url(scryfall_repository, "https://api.scryfall.com/sets", filename_out, storage_service=storage_service)
    return {"filename": str(filename_out)}

@ServiceRegistry.register("staging.scryfall.download_cards_bulk"
                          , api_repositories=["scryfall"]
                          , db_repositories=["ops"]
                          , storage_services=["scryfall"])
async def download_cards_bulk(
    scryfall_repository: ScryfallAPIRepository,
    ops_repository: OpsRepository,
    ingestion_run_id: int = None,
    uris_to_download: list[dict] | None = None,
    resource_type: str = "default_cards",
    storage_service: StorageService = None,
) -> dict:
    """Stream-download Scryfall card bulk files to disk.

    uris_to_download: list of {resource_id, download_uri, last_modified, external_type}
    resource_type: only download items whose external_type matches this value
    """
    if not uris_to_download:
        logger.info("No bulk URI changes — skipping card download", extra={"ingestion_run_id": ingestion_run_id})
        return {"file_name": None}
    filtered = [
        item["download_uri"]
        for item in uris_to_download
        # Key is "external_type" — matches the jsonb_build_object key produced by
        # update_bulk_scryfall_data_sql in ops/scryfall_data.py (not "type").
        if isinstance(item, dict) and item.get("external_type") == resource_type
    ]

    if not filtered:
        logger.info("No URI matching resource_type — skipping card download",
                    extra={"resource_type": resource_type, "ingestion_run_id": ingestion_run_id})
        return {"file_name": None}

    async with track_step(ops_repository, ingestion_run_id, "download_cards_bulk", error_code="download_failed"):
        # filtered contains exactly one URI for the matched resource_type;
        # stream_download_scryfall_json_from_uris expects a single string, not a list.
        result = await stream_download_scryfall_json_from_uris(scryfall_repository, filtered[0], storage_service, ingestion_run_id)
    return {"file_name": result["files_saved"][0]}

import os, shutil
@ServiceRegistry.register("staging.scryfall.delete_old_scryfall_folders",
                          storage_services=["scryfall"]
                         )
async def delete_old_scryfall_folders(keep: int = 3
                               , storage_service: StorageService = None):
    """Delete Scryfall raw files older than specified days to keep"""
    list_default_cards = await storage_service.list_directory("*default-card*")
    if not list_default_cards:
        logger.warning("No default card files found; nothing to clean")
        return {"deleted_runs": []}

    def _parse_date(filename: str) -> str:
        parts = filename.split("_")
        return parts[1] if len(parts) >= 2 else ""

    list_default_cards.sort(key=lambda p: _parse_date(p), reverse=True)  # newest first
    to_delete = list_default_cards[keep:]
    results = await storage_service.delete_files([str(d) for d in to_delete])
    return {"deleted_runs": results, "kept": [str(d) for d in list_default_cards[:keep]]}

@ServiceRegistry.register("staging.scryfall.download_and_load_migrations",
                         api_repositories=["scryfall"], db_repositories=["card", "ops"])
async def download_scryfall_migrations(
        scryfall_repository: ScryfallAPIRepository,
        card_repository,
        ops_repository: OpsRepository,
        ingestion_run_id: int = None,
):
    """Download Scryfall card migrations and load into the database"""
    async with track_step(ops_repository, ingestion_run_id, "download_and_load_migrations", error_code="migration_failed"):
        buffer = await scryfall_repository.migrations_to_bytes_buffer()
        status = await card_repository.copy_migrations(buffer)
    logger.info("Migrations loaded", extra={"ingestion_run_id": ingestion_run_id, "status": status})
    return {"migration_load_status": status}
    

