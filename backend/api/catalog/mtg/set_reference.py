from dataclasses import dataclass
from  datetime import datetime
from fastapi import APIRouter, File, Query, Depends, HTTPException, Response, UploadFile, UploadFile, logger, status
from typing import Any, Callable, Dict, List, Annotated, Optional
import tempfile, os, logging

import ijson
from backend.new_services.service_manager import ServiceManager
from backend.dependancies.service_deps import get_service_manager
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
                  , service_manager: ServiceManager = Depends(get_service_manager)):
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
                    limit: Annotated[int, Query(le=100)]=100,
                    offset: int=0,
                    ids: Annotated[Optional[List[str]], Query(title='Optional set_ids')]=None,
                    service_manager: ServiceManager = Depends(get_service_manager)):
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



@router.delete('/{set_id}', status_code=status.HTTP_204_NO_CONTENT, description='Delete a set by its ID')
async def delete_set(
                    set_id : UUID
                    , service_manager: ServiceManager = Depends(get_service_manager)
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
                     , service_manager: ServiceManager = Depends(get_service_manager)):
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
                      , service_manager: ServiceManager = Depends(get_service_manager)):
    try:
        await service_manager.execute_service(
            "card_catalog.set.create_bulk",
            sets=sets
        )
    except HTTPException:
        raise
    except Exception:
        raise

@router.post("/upload-file")
async def upload_large_sets_json(file: UploadFile = File(...)
                                 , service_manager: ServiceManager = Depends(get_service_manager)):
    try:
        # Validate file type
        if not file.filename.endswith('.json'):
            raise HTTPException(
                status_code=400,
                detail="Only JSON files are supported"
            )
        # Check file size (optional limit)
        max_size =  1024 * 1024 * 1024  # 1GB default
        logger.info(f"Processing file upload: {file.filename}")
        
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as temp_file:
            content = await file.read()
            
            if len(content) > max_size:
                raise HTTPException(
                    status_code=400,
                    detail=f"File too large. Maximum size: {max_size / 1024 / 1024:.1f}MB"
                )
            
            temp_file.write(content)
            temp_file_path = temp_file.name
        
        # Process file using enhanced service
        try:
            result = await service_manager.execute_service(
                "card_catalog.set.process_large_json",
                file_path=temp_file_path,
            )
            
            # Clean up temp file
            os.unlink(temp_file_path)
            
            # Convert result to dict if it's a stats object
            if hasattr(result, 'to_dict'):
                result_data = result.to_dict()
            else:
                result_data = result
            return ApiResponse(
                data={
                    "filename": file.filename,
                    "file_size_mb": round(len(content) / 1024 / 1024, 2),
                    "processing_stats": result_data
                },
                message=f"File '{file.filename}' processed successfully"
            )
            
        except Exception as processing_error:
            # Clean up temp file on error
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            raise processing_error
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process file upload '{file.filename}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")
  

@router.put('/{set_id}')
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