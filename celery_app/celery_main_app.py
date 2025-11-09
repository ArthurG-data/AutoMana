import os, logging, sys
from celery import Celery
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

current_dir = os.path.dirname(__file__)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

celery_app = Celery('etl')
celery_app.config_from_object('celery_app.celeryconfig')

try:
    celery_app.connection().ensure_connection(max_retries=3)
    logging.info("Connected to the message broker successfully.")
except Exception as e:
    logging.error(f"Failed to connect to the message broker: {e}")

@celery_app.task
def hello():
    return "Hello, World!"
