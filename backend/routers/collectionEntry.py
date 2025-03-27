from fastapi import APIRouter, Depends
from backend.models.collections import CollectionEntry
from psycopg2.extensions import connection
from typing import Annotated
from backend.dependancies import cursorDep

router =  APIRouter(
    prefix = '/inventory',
    tags = ['inventory'],
    dependencies=[]
)



@router.post('/', response_model=CollectionEntry)
async def add_entry( conn : cursorDep, new_entry : CollectionEntry):
    return new_entry