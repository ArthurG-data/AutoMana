from celery import shared_task, chain
import logging
from celery_app.main import run_service

from datetime import datetime

logger = logging.getLogger(__name__)

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True)
def daily_scryfall_data_pipeline(self):
    run_key = f"scryfall_daily:{datetime.utcnow().date().isoformat()}"
    num_steps = 9
    wf = chain(
        run_service.s("staging.scryfall.start_pipeline",
                      pipeline_name="scryfall_daily",
                      source_name="scryfall",
                      run_key=run_key,
                      celery_task_id=self.request.id,
                      num_steps=num_steps),

        run_service.s("staging.scryfall.get_bulk_data_uri"),#get the uri for the bulk data manifest
        run_service.s("staging.scryfall.download_bulk_manifests"),#download the bulk data manifest
        run_service.s("staging.scryfall.update_data_uri_in_ops_repository"),#from the manifest, update the db and get the list of uris to download
        run_service.s("staging.scryfall.download_sets", save_dir="/data/scryfall/raw_files/"),
        run_service.s("card_catalog.set.process_large_sets_json", update_run = True), 
        run_service.s("staging.scryfall.download_cards_bulk", save_dir="/data/scryfall/raw_files/"),
        run_service.s("card_catalog.card.process_large_json", update_run = True),
        run_service.s("staging.scryfall.pipeline_finish")
    )
    return wf.apply_async().id
 