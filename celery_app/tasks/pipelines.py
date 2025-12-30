from celery import shared_task, chain
from backend.core.service_manager import ServiceManager
import logging
from celery_app.main import run_service

logger = logging.getLogger(__name__)

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True)
def daily_scryfall_data_pipeline(self):
    workflow = chain(
        run_service.s("staging.scryfall.full_data_download_process", save_dir="/data/scryfall/raw_files/"),
        # run_service.s("staging.scryfall.update_ops_registry"),
        # run_service.s("card_catalog.set.process_large_sets_json", file_path="/data/scryfall/raw_files/sets.json"),
        # run_service.s("card_catalog.card.process_large_cards_json", file_path="/data/scryfall/raw_files/cards.json"),
    )
    return workflow.apply_async().id
 