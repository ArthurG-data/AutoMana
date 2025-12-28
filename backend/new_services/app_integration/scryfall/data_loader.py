import aiohttp, logging
from backend.repositories.app_integration.scryfall.ApiScryfall import ScryfallAPIRepository
from backend.repositories.ops.ops_repository import OpsRepository
import pathlib

from datetime import datetime, time
from backend.core.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)
#get manifest
#update database with uris

#download from uris and save to disk


async def get_and_update_scryfall_bulk_data_uris(ops_repository: OpsRepository
                                               , scryfall_repository: ScryfallAPIRepository):
    pass

async def get_scryfall_bulk_data_uri(ops_repository: OpsRepository) -> str:
    """Retrieve Scryfall bulk data URIs from the database"""
    bulk_uri = await ops_repository.get_bulk_data_uri()
    if not bulk_uri:
        raise ValueError("No bulk data URI found in the database.")
    return bulk_uri

async def download_scryfall_bulk_manifests(repository: ScryfallAPIRepository, bulk_uri: str) -> str:
    """Download the Scryfall bulk data manifest"""
    return await repository.download_data_from_url(bulk_uri)
    
async def download_scryfall_from_url(repository: ScryfallAPIRepository
                                  , url: str
                                  , filename_out: pathlib.Path):
    """Download Scryfall data from a given URL and save to specified path"""
    date_str = datetime.utcnow().strftime("%Y%m%d")
    filename_out = filename_out.parent / f"{date_str}_{filename_out.name}"
    filename_out.parent.mkdir(parents=True, exist_ok=True)
    result = await repository.download_data_from_url(url)
    if result.get("data"):
        filename_out.parent.mkdir(parents=True, exist_ok=True)
        with open(filename_out, "w", encoding="utf-8") as f:
            import json
            json.dump(result["data"], f)

        return {"status": "success", "file_saved": str(filename_out)}
    else:
        return {"status": "failed", "reason": "No data returned from Scryfall"}

async def stream_download_scryfall_json_from_uris(repository: ScryfallAPIRepository
                                            ,uris: list[str]
                                           , save_dir: pathlib.Path):
    """Download Scryfall bulk data from given URIs and save to specified directory"""
    date_str = datetime.utcnow().strftime("%Y%m%d")
    saved = []
    save_dir = pathlib.Path(save_dir)
    for url in uris:
        name = url.split("/")[-1]  # ends with .json or .json.gz
        out = save_dir / f"{date_str}_{name}"
        await repository.stream_download(url, out)
        saved.append(str(out))

    return {"status": "success", "files_saved": saved}

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
    bulk_items_changed =manifests["data"]["data"]
    download_uris = [
        item["download_uri"]
        for item in bulk_items_changed
        if item["type"] in ("all_cards")
        ]
    logger.info(f"Downloading Scryfall data from {download_uris}...")
    #download sets
    out_path_sets = save_dir / "sets.json"
    set_result = await download_scryfall_from_url(scryfall_repository, "https://api.scryfall.com/sets", out_path_sets)
    card_result = await stream_download_scryfall_json_from_uris(scryfall_repository, download_uris, save_dir)
    return {
        "sets_download": set_result,
        "cards_download": card_result
    }
    