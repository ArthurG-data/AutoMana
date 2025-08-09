from fastapi import APIRouter, HTTPException, Depends
from typing import List
from uuid import UUID
from backend.schemas.collections.collection import CreateCollection, UpdateCollection, PublicCollection, PublicCollectionEntry, UpdateCollectionEntry, NewCollectionEntry
from backend.dependancies.auth import currentActiveUser
from backend.new_services.service_manager import ServiceManager
from backend.dependancies.service_deps import get_service_manager


router = APIRouter(
     prefix='/collection',
    tags=['collection'],
    responses={404:{'description':'Not found'}}
)


@router.post('/')
async def add_collection(
    created_collection: CreateCollection, 
    current_user: currentActiveUser,
    service_manager: ServiceManager = Depends(get_service_manager)
) -> dict:
    return await service_manager.execute_service(
        "card_catalog.collection.add", created_collection, current_user)

@router.delete('/{collection_id}', status_code=200)
async def remove_collection(
    collection_id: str, 
    current_user: currentActiveUser,
    service_manager: ServiceManager = Depends(get_service_manager)
):
    return await service_manager.execute_service(
        "card_catalog.collection.delete", collection_id, current_user)


@router.get('/{collection_id}', response_model=PublicCollection)
async def get_collection(
    collection_id: str, 
    current_user: currentActiveUser,
    service_manager: ServiceManager = Depends(get_service_manager)
):
    return await service_manager.execute_service(
        "card_catalog.collection.get", collection_id, current_user)

@router.get('/', response_model=List[PublicCollection])
async def get_collection(
    current_user: currentActiveUser,
    service_manager: ServiceManager = Depends(get_service_manager)
):
    collections = await service_manager.execute_service(
        "card_catalog.collection.get_many", current_user)
    return collections

@router.put('/{collection_id}', status_code=204)
async def change_collection(
    collection_id: str, 
    updated_collection: UpdateCollection, 
    current_user: currentActiveUser,
    service_manager: ServiceManager = Depends(get_service_manager)
):
    return await service_manager.execute_service(
        "card_catalog.collection.update", collection_id, updated_collection, current_user)
    
@router.delete('{collection_id}/{entry_id}')
async def delete_entry(
    collection_id: str, 
    entry_id: UUID,
    service_manager: ServiceManager = Depends(get_service_manager)
):
    return await service_manager.execute_service(
        "card_catalog.collection.delete_entry", collection_id, entry_id)
    
@router.get('{collection_id}/{entry_id}', response_model=PublicCollectionEntry)
async def get_entry(
    collection_id: str, 
    entry_id: UUID,
    service_manager: ServiceManager = Depends(get_service_manager)
):
    return await service_manager.execute_service(
        "card_catalog.collection.get_entry", collection_id, entry_id)
    
    query = """ SELECT c.item_id, c.collection_id,  c.unique_card_id, c.is_foil, c.purchase_date,c.purchase_price, rc.condition_description AS condition
                FROM collectionItems c
                JOIN Ref_Condition rc ON rc.condition_code = c.condition
                WHERE item_id = %s
            """
    try:
        return  execute_select_query(conn, query, (entry_id,), select_all=False)
    except Exception:
            raise 

