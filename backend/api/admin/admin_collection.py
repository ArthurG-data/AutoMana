from fastapi import APIRouter
from backend.database.get_database import cursorDep
from backend.modules.public.collections.models import PublicCollection
from backend.modules.admin.admin_collections_services import collect_collection, delete_collection
from typing import List

collection_router = APIRouter(prefix='/collections',
                             tags=['admin-collection'],)

@collection_router.delete('/{collection_id}')
async def remove_collection(collection_id : str, connection : cursorDep):
    return delete_collection(collection_id, connection)


@collection_router.get('/{collection_id}', response_model=PublicCollection)
async def get_collection(collection_id : str, conn : cursorDep):
    return collect_collection(collection_id, conn)

@collection_router.get('/', response_model=List[PublicCollection])
async def get_collection(conn : cursorDep):
    return collect_collection(conn)

