import psycopg2 
from psycopg2.extras import RealDictCursor
from fastapi import HTTPException, Depends
from typing import Annotated, Any
import os, dotenv
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)



def connect_db(host, database, user, password):
    try:
        connection = psycopg2.connect(
            host=host,
            database=database,
            user=user,
            password=password,
            cursor_factory=RealDictCursor
        )
        print("Database connection was successful")
        return connection
    except Exception:
        raise HTTPException(status_code=500, detail='Oups, could not connect the database')

def get_db():
    print(os.getenv('POSTGRES_USER'))
    db = connect_db(os.getenv('POSTGRES_HOST'), os.getenv('POSTGRES_DB'), os.getenv('POSTGRES_USER'), os.getenv('POSTGRES_PASSWORD'))
    try:
        yield db
    except HTTPException:
        raise
    finally:
        db.close()

def get_cursor(db : Annotated[psycopg2.extensions.connection, Depends(get_db)]):
    cursor = db.cursor()
    try:
        yield cursor
    finally:
        cursor.close()
