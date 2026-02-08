from celery import shared_task, chain
import logging
from celery_app.main import run_service
from datetime import datetime

logger = logging.getLogger(__name__)

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True)
def daily_scryfall_data_pipeline(self):
    run_key = f"scryfall_daily:{datetime.utcnow().date().isoformat()}"
    wf = chain(
        run_service.s("staging.scryfall.start_pipeline",#new test
                      pipeline_name="scryfall_daily",
                      source_name="scryfall",
                      run_key=run_key,
                      celery_task_id=self.request.id
                      ),
        run_service.s("staging.scryfall.get_bulk_data_uri"),#get the uri for the bulk data manifest
        run_service.s("staging.scryfall.download_bulk_manifests"),#download the bulk data manifest
        run_service.s("staging.scryfall.update_data_uri_in_ops_repository"),#from the manifest, update the db and get the list of uris to download
        run_service.s("staging.scryfall.download_sets", save_dir="/data/scryfall/raw_files/"),
        run_service.s("card_catalog.set.process_large_sets_json", update_run = True), 
        run_service.s("staging.scryfall.download_cards_bulk"),
        run_service.s("card_catalog.card.process_large_json"),
        run_service.s("ops.pipeline_services.finish_run", status="success"),
        run_service.s("staging.scryfall.delete_old_scryfall_folders", keep=3),
    )
    return wf.apply_async().id
 
@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True)
def mtgStock_download_pipeline(self):
    run_key = f"mtgStock_All:{datetime.utcnow().date().isoformat()}"
    wf = chain(
        run_service.s("ops.pipeline_services.start_run",#new test
                      pipeline_name="mtg_stock_all",
                      source_name="mtgStock",
                      run_key=run_key,
                      celery_task_id=self.request.id
                      ),
        run_service.s("mtg_stock.data_staging.bulk_load",
                      root_folder="/data/mtgstocks/raw/prints/",
                      batch_size=1000
                      ),
        run_service.s("mtg_stock.data_staging.from_raw_to_staging"),
        run_service.s("mtg_stock.data_staging.from_staging_to_dim"),
        run_service.s("mtg_stock.data_staging.from_dim_to_prices"),
        run_service.s("ops.pipeline_services.finish_run", status="success" )
    )
    return wf.apply_async().id


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True)
def daily_mtgjson_data_pipeline(self):
    run_key = f"mtgjson_daily:{datetime.utcnow().date().isoformat()}"
    logger.info("Starting MTGJSON data pipeline with run key: %s", run_key)
    wf = chain(
        run_service.s("ops.pipeline_services.start_run",
                       pipeline_name="mtgjson_daily",
                       run_key=run_key,
                      source_name="mtgjson",
                      celery_task_id=self.request.id
                      ),
        run_service.s("mtgjson.data.staging.today"),
        run_service.s("ops.pipeline_services.finish_run", status="success" )
    )
    return wf.apply_async().id