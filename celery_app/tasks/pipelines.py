from celery import shared_task, chain
from backend.core.service_manager import ServiceManager
import logging
from celery_app.main import run_service

logger = logging.getLogger(__name__)
'''
@ServiceRegistry.register("staging.scryfall.full_data_download_process",
                         db_repositories=["ops"], api_repositories=["scryfall"])
async def full_scryfall_data_download_process(ops_repository: OpsRepository
                                            , scryfall_repository: ScryfallAPIRepository
                                            , save_dir: str):
    """Full process to download Scryfall bulk data and save to disk , set and cards data"""
    save_dir = pathlib.Path(save_dir)
    bulk_uri = await get_scryfall_bulk_data_uri(ops_repository)
    manifests = await download_scryfall_bulk_manifests(scryfall_repository, bulk_uri)# should return multuple uris
    #update database with new uris if needed, and check if the file has changed
    bulk_items =manifests["data"]["data"]
    uri_to_download = await ops_repository.update_bulk_data_uri_return_new(bulk_items, source_id=1)
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
    
'''


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True)
def daily_scryfall_data_pipeline(self):
    workflow = chain(
        run_service.s("ops.scryfall.start_pipeline"),
        run_service.s("staging.scryfall.get_bulk_data_uri"),
        run_service.s("staging.scryfall.full_data_download_process", save_dir="/data/scryfall/raw_files/"),
        run_service.s("staging.scryfall.download_bulk_manifests", bulk_uri=[]),
        run_service.s("staging.scryfall.update_data_uri_in_ops_repository", uris=[], save_dir="/data/scryfall/raw_files/"),
        run_service.s("staging.scryfall.download_data_from_url", save_dir="/data/scryfall/raw_files/"),
        run_service.s("staging.scryfall.stream_download_json_from_uris", uris=[], save_dir="/data/scryfall/raw_files/"),
    )
    return workflow.apply_async().id
 