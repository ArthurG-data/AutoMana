
from celery import shared_task
from automana.worker.main import run_service
from automana.worker.ressources import get_state
import requests

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True)
def daily_summary_analytics_task(self):
    settings = get_state().settings
    result = run_service("analytics.daily_summary.generate_report")
    webhook = settings.DISCORD_WEBHOOK_URL
    
    # Format the result as a readable message
    message = f"""**Daily Summary Report**
📊 New Sets: {result.get('new_sets_count', 0)}
🃏 New Cards: {result.get('new_cards_count', 0)}
📦 Total Cards: {result.get('total_cards_count', 0)}
📚 Total Sets: {result.get('total_sets_count', 0)}
🔄 Ingestion Runs: {len(result.get('ingestion_runs', []))}
"""
    
    response = requests.post(webhook, json={"content": message})
    response.raise_for_status()
    
    return {"status": "success", "message": "Daily summary sent to Discord"}