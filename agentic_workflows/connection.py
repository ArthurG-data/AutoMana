from sqlalchemy import create_engine
from contextlib import contextmanager
import os,dotenv, logging
from pathlib import Path

env_path = Path(__file__).parent.parent / "agentic_workflows" /".env"
dotenv.load_dotenv(env_path)

logging.basicConfig(level=logging.INFO)

engine = None

def get_engine():
    global engine
    logging.info("Getting database engine for user: %s", os.getenv('POSTGRES_USER'))
    if engine is None:
        connection_url = f"postgresql+psycopg2://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@localhost:5432/{os.getenv('POSTGRES_DB')}"
        engine = create_engine(connection_url)
    return engine

@contextmanager
def get_connection():
    engine = get_engine()
    connection = engine.connect()
    try:
        yield connection
    finally:
        connection.close()