import aiohttp, logging
from backend.repositories.app_integration.scryfall.ApiScryfall import ScryfallAPIRepository
from backend.repositories.ops.ops_repository import OpsRepository
import pathlib

from datetime import datetime, time
from backend.core.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)

#start pipeline
@ServiceRegistry.register("staging.scryfall.start_pipeline",
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

@ServiceRegistry.register("staging.scryfall.pipeline_finish", db_repositories=["ops"])
async def pipeline_finish(ops_repository: OpsRepository, ingestion_run_id: int, status: str = "success", notes: str | None = None):
    """Finish the Scryfall data ingestion pipeline by updating the run status in the Ops repository."""
    await ops_repository.finish_run(ingestion_run_id, status=status, notes=notes)
    return {"status": status}

#get bulk data uri
@ServiceRegistry.register("staging.scryfall.get_bulk_data_uri",
                         db_repositories=["ops"])
async def get_scryfall_bulk_data_uri(ops_repository: OpsRepository
                                      , ingestion_run_id: int) -> str:
    """Retrieve Scryfall bulk data URIs from the database"""
    bulk_uri = await ops_repository.get_bulk_data_uri()
    if not bulk_uri:
        await ops_repository.update_run(ingestion_run_id, status="failed", current_step="get_bulk_data_uri", error_code="no_bulk_uri", error_details={"message": "No bulk data URI found in the database."})
        raise ValueError("No bulk data URI found in the database.")
    await ops_repository.update_run(ingestion_run_id, status="running", current_step="get_bulk_data_uri", progress=10.0)
    return {"bulk_uri": bulk_uri}

#download bulk manifests
@ServiceRegistry.register("staging.scryfall.download_bulk_manifests",
                         api_repositories=["scryfall"], db_repositories=["ops"])
async def download_scryfall_bulk_manifests( ops_repository: OpsRepository
                                            ,scryfall_repository: ScryfallAPIRepository
                                           , bulk_uri: str
                                           , ingestion_run_id: int) -> str:
    """Download the Scryfall bulk data manifest"""
    try:
        manifests = await scryfall_repository.download_data_from_url(bulk_uri
                                                                )
    except Exception as e:
        await ops_repository.update_run(ingestion_run_id, status="failed", current_step="download_bulk_manifests", error_code="download_failed", error_details={"message": str(e)})
        raise e
    if not manifests.get("data"):
        await ops_repository.update_run(ingestion_run_id, status="failed", current_step="download_bulk_manifests", error_code="no_manifest_data", error_details={"message": "Failed to download Scryfall bulk data manifest."})
        raise ValueError("Failed to download Scryfall bulk data manifest.")
    await ops_repository.update_run(ingestion_run_id,status="running", current_step="download_bulk_manifests", progress=30.0)
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
    try:
        result = await ops_repository.update_bulk_data_uri_return_new(items, ingestion_run_id)
    except Exception as e:
        await ops_repository.update_run(ingestion_run_id, status="failed", current_step="update_data_uri_in_ops_repository", error_code="update_failed", error_details={"message": str(e)})
        raise e
    bulk_items_changed = result.get("changed", [])
    if not bulk_items_changed or len(bulk_items_changed) == 0:
        logger.info("No changes in Scryfall bulk data URIs. No download needed.")
    return {'uris_to_download':bulk_items_changed }

@ServiceRegistry.register("staging.scryfall.download_sets", api_repositories=["scryfall"], db_repositories=["ops"])
async def download_sets(
    scryfall_repository: ScryfallAPIRepository,
    ops_repository: OpsRepository,
    ingestion_run_id: int,
    save_dir: str,
) -> dict:
    #

    try:
        save_dir = pathlib.Path(save_dir)
        out_path = save_dir / str(ingestion_run_id) / "sets.json"
        await download_scryfall_from_url(scryfall_repository, "https://api.scryfall.com/sets", out_path)
    except Exception as e:
        await ops_repository.update_run(ingestion_run_id, status="failed", current_step="download_sets", error_code="download_failed", error_details={"message": str(e)})
        raise e
    await ops_repository.update_run(ingestion_run_id, current_step="download_sets", progress=50.0)
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
        await ops_repository.update_run(ingestion_run_id, current_step="download_cards_bulk", progress=87.5)
    except Exception as e:
        await ops_repository.update_run(ingestion_run_id, status="failed", current_step="download_cards_bulk", error_code="download_failed", error_details={"message": str(e)})
        raise e 
    return {"file_path_card" : result["files_saved"][0]}


'''
@ServiceRegistry.register("staging.scryfall.full_data_download_process",
                         db_repositories=["ops"], api_repositories=["scryfall"])
async def full_scryfall_data_download_process(ops_repository: OpsRepository
                                            , scryfall_repository: ScryfallAPIRepository
                                            , save_dir: str):
    """Full process to download Scryfall bulk data and save to disk , set and cards data"""
    try:
        save_dir = pathlib.Path(save_dir)
        bulk_uri = await get_scryfall_bulk_data_uri(ops_repository)
        manifests = await download_scryfall_bulk_manifests(scryfall_repository, bulk_uri)# should return multuple uris
        #update database with new uris if needed, and check if the file has changed
        bulk_items =manifests["data"]
        print(f"Bulk items: {bulk_items}")
        uri_to_download = await update_data_uri_in_ops_repository(ops_repository, bulk_items, source_id=1)
        bulk_items_changed = uri_to_download.get("changed", [])
        if not bulk_items_changed or len(bulk_items_changed) == 0:
            logger.info("No changes in Scryfall bulk data URIs. No download needed.")
            return {"status": "no_changes"}
        download_uris = [
            item["download_uri"]
            for item in bulk_items_changed
            if item["type"] in ("default_cards")
            ]
        logger.info(f"Downloading Scryfall data from {download_uris}...")
        #download sets, if no new cards, no new sets
        out_path_sets = save_dir / "sets.json"
        set_result = await download_scryfall_from_url(scryfall_repository, "https://api.scryfall.com/sets", out_path_sets)
        card_result = await stream_download_scryfall_json_from_uris(scryfall_repository, download_uris, save_dir)
        return {
            "sets_download": set_result,
            "cards_download": card_result
        }
    except Exception as e:
        raise e
'''