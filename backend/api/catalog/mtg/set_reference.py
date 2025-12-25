from dataclasses import dataclass
from  datetime import datetime
from fastapi import APIRouter, File, Query, Depends, HTTPException, Response, UploadFile, UploadFile, logger, status
from typing import Any, Callable, Dict, List, Annotated, Optional
import tempfile, os, logging

import ijson
from backend.dependancies.service_deps import ServiceManagerDep
from backend.request_handling.StandardisedQueryResponse import (    ApiResponse
                                                                ,PaginatedResponse
                                                                ,ErrorResponse
                                                                ,PaginationInfo)
from uuid import UUID
logger = logging.getLogger(__name__)
from backend.schemas.card_catalog.set import NewSet, NewSets, UpdatedSet

router = APIRouter(
        prefix="/set-reference",
        tags=['sets'], 
        responses={
            404: {'description': 'Not found', 'model': ErrorResponse},
            500: {'description': 'Internal server error', 'model': ErrorResponse}
        }
)

@router.get('/{set_id}', response_model=ApiResponse)
async def get_set(set_id: UUID
                  , service_manager: ServiceManagerDep):
    try:
        result = await service_manager.execute_service("card_catalog.set.get", set_id=set_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Set not found")
        
        return ApiResponse(
            success=True,
            data=result,
            message="Set retrieved successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/')
async def get_sets(
                    service_manager: ServiceManagerDep,
                    limit: int = Query(default=100, le=100, ge=1),
                    offset: int = Query(default=0, ge=0),
                    ids: Optional[List[str]] = Query(default=None, title='Optional set_ids')
                    ):
    try:
        result = await service_manager.execute_service("card_catalog.set.get_all"
                                                       , limit=limit
                                                       , offset=offset
                                                       , ids=ids)
        return PaginatedResponse(
            success=True,
            data=result,
            message="Sets retrieved successfully",
            pagination=PaginationInfo(
                limit=limit,
                offset=offset,
                total_count=len(result),
                has_next=len(result) > limit,
                has_previous=offset > 0
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.delete('/{set_id}'
               , status_code=status.HTTP_204_NO_CONTENT
               , description='Delete a set by its ID')
async def delete_set(
                    set_id : UUID
                    , service_manager: ServiceManagerDep
                    ):
    try:
        await service_manager.execute_service(
            "card_catalog.set.delete",
            set_id=set_id
        )   
    except HTTPException:
        raise
    except Exception:
        raise

@router.post('/', description='An endpoint to add a new set', status_code=status.HTTP_201_CREATED)
async def insert_set(new_set : NewSet
                     , service_manager: ServiceManagerDep):
    try:
        await service_manager.execute_service(
            "card_catalog.set.add",
            new_set=new_set
        )
    except HTTPException:
        raise
    except Exception:
        raise
  
@router.post('/bulk', description='An endpoint to add multiple sets to the database', status_code=status.HTTP_201_CREATED)
async def insert_sets(sets : NewSets
                      , service_manager: ServiceManagerDep):
    try:
        await service_manager.execute_service(
            "card_catalog.set.create_bulk",
            sets=sets
        )
    except HTTPException:
        raise
    except Exception:
        raise

@router.put('/{set_id}')
async def update_set(
                    set_id  : UUID, 
                    update_set : UpdatedSet,
                    service_manager: ServiceManagerDep):
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