import  logging
from backend.repositories.app_integration.scryfall.ApiScryfall import ScryfallAPIRepository
from backend.repositories.ops.ops_repository import OpsRepository
import pathlib

from datetime import datetime
from backend.core.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)
print("✓ data_loader.py imported successfully")


@ServiceRegistry.register("staging.scryfall.pipeline_finish"
                          , db_repositories=["ops"])
async def pipeline_finish(ops_repository: OpsRepository
                          , ingestion_run_id: int
                          , status: str = "success"
                          , notes: str | None = None):
    """Finish the Scryfall data ingestion pipeline by updating the run status in the Ops repository."""
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
                                      , ingestion_run_id: int
                                     ) -> str:
    """Retrieve Scryfall bulk data URIs from the database"""
    await ops_repository.update_run(ingestion_run_id, status="running", current_step="get_bulk_data_uri")
    bulk_uri = await ops_repository.get_bulk_data_uri()
    if not bulk_uri:
        await ops_repository.update_run(ingestion_run_id, status="failed", current_step="get_bulk_data_uri", error_code="no_bulk_uri", error_details={"message": "No bulk data URI found in the database."})
        raise ValueError("No bulk data URI found in the database.")
    await ops_repository.update_run(ingestion_run_id, status="success", current_step="get_bulk_data_uri")
    return {"bulk_uri": bulk_uri}

#download bulk manifests
@ServiceRegistry.register("staging.scryfall.download_bulk_manifests",
                         api_repositories=["scryfall"], db_repositories=["ops"])
async def download_scryfall_bulk_manifests( ops_repository: OpsRepository
                                            ,scryfall_repository: ScryfallAPIRepository
                                           , bulk_uri: str
                                           , ingestion_run_id: int) -> str:
    """Download the Scryfall bulk data manifest"""
    await ops_repository.update_run(ingestion_run_id
                                    , status="running"
                                    , current_step="download_bulk_manifests")
    try:
        manifests = await scryfall_repository.download_data_from_url(bulk_uri
                                                                )
    except Exception as e:
        await ops_repository.update_run(ingestion_run_id
                                        , status="failed"
                                        , current_step="download_bulk_manifests"
                                        , error_code="download_failed", error_details={"message": str(e)})
        raise e
    if not manifests.get("data"):
        await ops_repository.update_run(ingestion_run_id
                                        , status="failed"
                                        , current_step="download_bulk_manifests"
                                        , error_code="no_manifest_data"
                                        , error_details={"message": "Failed to download Scryfall bulk data manifest."})
        raise ValueError("Failed to download Scryfall bulk data manifest.")
    await ops_repository.update_run(ingestion_run_id
                                    ,status="success", current_step="download_bulk_manifests")
    print(manifests["data"])
    return {"items": manifests["data"]}

async def download_scryfall_from_url(repository: ScryfallAPIRepository
                                    , url: str
                                  , filename_out:  pathlib.Path
):
    """Download Scryfall data from a given URL and save to specified path"""

    filename_out.parent.mkdir(parents=True, exist_ok=True)
    result = await repository.download_data_from_url(url)
    if result.get("data"):
        filename_out.parent.mkdir(parents=True, exist_ok=True)
        with open(filename_out, "w", encoding="utf-8") as f:
            import json
            json.dump(result["data"], f)
    return {"file_path": filename_out}
    
        

async def stream_download_scryfall_json_from_uris(repository: ScryfallAPIRepository
                                            ,uris: list[str]
                                           , save_dir: pathlib.Path
                                           , ingestion_run_id: int):
    """Download Scryfall bulk data from given URIs and save to specified directory"""
    saved = []
    save_dir = pathlib.Path(save_dir)
    for url in uris:
        name = url.split("/")[-1]  # ends with .json or .json.gz
        out = save_dir / str(ingestion_run_id) / name
        await repository.stream_download(url, out)
        saved.append(str(out))

    return {"files_saved": saved}


@ServiceRegistry.register("staging.scryfall.update_data_uri_in_ops_repository",
                         db_repositories=["ops"])
async def update_data_uri_in_ops_repository(ops_repository: OpsRepository
                                            , items: dict
                                            , ingestion_run_id: int):
    """Update the bulk data URIs in the Ops repository"""
    await ops_repository.update_run(ingestion_run_id, status="running", current_step="update_data_uri_in_ops_repository")
    try:
        result = await ops_repository.update_bulk_data_uri_return_new(items, ingestion_run_id)
    except Exception as e:
        await ops_repository.update_run(ingestion_run_id, status="failed", current_step="update_data_uri_in_ops_repository", error_code="update_failed", error_details={"message": str(e)})
        raise e
    bulk_items_changed = result.get("changed", [])
    if not bulk_items_changed or len(bulk_items_changed) == 0:
        logger.info("No changes in Scryfall bulk data URIs. No download needed.")
    await ops_repository.update_run(ingestion_run_id, status="success", current_step="update_data_uri_in_ops_repository")
    return {'uris_to_download':bulk_items_changed }

@ServiceRegistry.register("staging.scryfall.download_sets", api_repositories=["scryfall"], db_repositories=["ops"])
async def download_sets(
    scryfall_repository: ScryfallAPIRepository,
    ops_repository: OpsRepository,
    ingestion_run_id: int,
    save_dir: str,
) -> dict:
    #
    await ops_repository.update_run(ingestion_run_id, status="running", current_step="download_sets")
    try:
        save_dir = pathlib.Path(save_dir)
        out_path = save_dir / str(ingestion_run_id) / "sets.json"
        await download_scryfall_from_url(scryfall_repository, "https://api.scryfall.com/sets", out_path)
    except Exception as e:
        await ops_repository.update_run(ingestion_run_id, status="failed", current_step="download_sets", error_code="download_failed", error_details={"message": str(e)})
        raise e
    await ops_repository.update_run(ingestion_run_id, current_step="download_sets")
    return {"file_path": str(out_path)}

@ServiceRegistry.register("staging.scryfall.download_cards_bulk", api_repositories=["scryfall"], db_repositories=["ops"])
async def download_cards_bulk(
    scryfall_repository: ScryfallAPIRepository,
    ops_repository: OpsRepository,
    ingestion_run_id: int,
    uris_to_download: list[str],
    save_dir: str,
) -> dict:
    

    if not uris_to_download:
        return {"file_path_card": "NO CHANGES"}
    try:
        result = await stream_download_scryfall_json_from_uris(scryfall_repository, uris_to_download, pathlib.Path(save_dir), ingestion_run_id)
        await ops_repository.update_run(ingestion_run_id, current_step="download_cards_bulk")
    except Exception as e:
        await ops_repository.update_run(ingestion_run_id, status="failed", current_step="download_cards_bulk", error_code="download_failed", error_details={"message": str(e)})
        raise e 
    return {"file_path_card" : result["files_saved"][0]}

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

