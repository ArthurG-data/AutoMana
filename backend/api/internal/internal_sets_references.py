from backend.schemas.card_catalog.set import   NewSet, UpdatedSet, NewSets
from fastapi import APIRouter, Response, status, File, UploadFile, Depends, HTTPException
from backend.database.get_database import cursorDep
from uuid import UUID
from backend.dependancies.general import get_service_manager
from backend.new_services.service_manager import ServiceManager
from backend.request_handling.StandardisedQueryResponse import ApiResponse

sets_router = APIRouter(
        prefix='/sets',
        tags=['internal-sets'], 
        responses={404:{'description':'Not found'}}
        
)

@sets_router.delete('/{set_id}', status_code=status.HTTP_204_NO_CONTENT, description='Delete a set by its ID')
async def delete_set(
                    set_id : UUID
                    , service_manager: ServiceManager = Depends(get_service_manager)
                    ):
    try:
        await service_manager.execute_service(
            "card_catalog.set.delete",
            set_id=set_id
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except HTTPException:
        raise
    except Exception:
        raise

@sets_router.post('/bulk', description='An endpoint to add multiple sets to the database')
async def insert_sets(sets : NewSets
                      , service_manager: ServiceManager = Depends(get_service_manager)):
    try:
        await service_manager.execute_service(
            "card_catalog.set.create_bulk",
            sets=sets
        )
        return Response(status_code=status.HTTP_201_CREATED)
    except HTTPException:
        raise
    except Exception:
        raise

@sets_router.post('/', description='An endpoint to add a new set')
async def insert_set(new_set : NewSet
                     , service_manager: ServiceManager = Depends(get_service_manager)):
    try:
        await service_manager.execute_service(
            "card_catalog.set.add",
            new_set=new_set
        )
        return Response(status_code=status.HTTP_201_CREATED)
    except HTTPException:
        raise
    except Exception:
        raise
  

@sets_router.post('/from_json')
async def insert_sets_from_file(
                                 parsed_sets #:NewSet=Depends(sets_from_json)
                                , service_manager: ServiceManager = Depends(get_service_manager)
                                ):
    #while be bytes
    try:
        await service_manager.execute_service(
            "card_catalog.set.create_bulk",
            sets=parsed_sets
        )
        return {'success'}
    except Exception as e:
        return [f"Error: {str(e)}"]


@sets_router.put('/{set_id}')
async def update_set(
                    set_id  : UUID, 
                    update_set : UpdatedSet,
                    service_manager: ServiceManager = Depends(get_service_manager)):
    try:
        await service_manager.execute_service(
            "card_catalog.set.update",
            set_id=set_id,
            update_set=update_set
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except HTTPException:
        raise
    except Exception:
        raise