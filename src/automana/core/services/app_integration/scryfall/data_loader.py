import  logging,pathlib
from automana.core.repositories.app_integration.scryfall.ApiScryfall_repository import ScryfallAPIRepository
from automana.core.repositories.ops.ops_repository import OpsRepository
from automana.core.services.ops.pipeline_services import track_step
from automana.core.storage import StorageService

from datetime import datetime
from automana.core.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)
print("âœ“ data_loader.py imported successfully")


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
    print(f"Started Scryfall data pipeline with run ID: {run_id}")
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
    print(manifests["data"])
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
                                            ,uris: list[str]
                                           , save_dir: pathlib.Path
                                           , ingestion_run_id: int = None):
    """Download Scryfall bulk data from given URIs and save to specified directory"""
    saved = []
    save_dir = pathlib.Path(save_dir)
    for url in uris:
        name = url.split("/")[-1]  # ends with .json or .json.gz
        out = save_dir / str(ingestion_run_id or "standalone") / name
        await repository.stream_download(url, out)
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
    bulk_items_changed = result.get("changed", [])
    if not bulk_items_changed:
        logger.info("No changes in Scryfall bulk data URIs. No download needed.")
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
    async with track_step(ops_repository, ingestion_run_id, "download_sets", error_code="download_failed"):
        await download_scryfall_from_url(scryfall_repository, "https://api.scryfall.com/sets", filename_out, storage_service=storage_service)
    return {"file_path": str(filename_out)}

@ServiceRegistry.register("staging.scryfall.download_cards_bulk", api_repositories=["scryfall"], db_repositories=["ops"])
async def download_cards_bulk(
    scryfall_repository: ScryfallAPIRepository,
    ops_repository: OpsRepository,
    ingestion_run_id: int = None,
    uris_to_download: list[str] = None,
    save_dir: str = None,
) -> dict:
    """Stream-download Scryfall card bulk files to disk"""
    if not uris_to_download:
        return {"file_path_card": "NO CHANGES"}
    async with track_step(ops_repository, ingestion_run_id, "download_cards_bulk", error_code="download_failed"):
        result = await stream_download_scryfall_json_from_uris(scryfall_repository, uris_to_download, pathlib.Path(save_dir), ingestion_run_id)
    return {"file_path_card": result["files_saved"][0]}

import os, shutil
@ServiceRegistry.register("staging.scryfall.delete_old_scryfall_folders",
                         )
async def delete_old_scryfall_folders(keep: int
                               , save_dir: pathlib.Path):
    """Delete Scryfall raw files older than specified days to keep"""
    root = pathlib.Path(save_dir)
    if not root.exists():
        logger.warning("Base dir %s missing; nothing to clean", root)
        return {"deleted_runs": []}

    run_dirs = [d for d in root.iterdir() if d.is_dir()]
    run_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)  # newest first
    to_delete = run_dirs[keep:]

    deleted = []
    for d in to_delete:
        shutil.rmtree(d, ignore_errors=False)
        deleted.append(str(d))
        logger.info("Deleted old run folder: %s", d)

    return {"deleted_runs": deleted, "kept": [str(d) for d in run_dirs[:keep]]}

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
    logger.info("Loaded Scryfall migrations into database with status: %s", status)
    return {"migration_load_status": status}
    

