from sqlalchemy import create_engine
from contextlib import contextmanager
import os,dotenv, logging

engine = None

def get_engine():
    global engine
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