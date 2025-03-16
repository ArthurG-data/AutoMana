import psycopg2 
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from fastapi import HTTPException, Depends
from typing import Annotated, Any


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
    db = connect_db('localhost', 'postgres', 'postgres', 'Pre45tkJ')
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
