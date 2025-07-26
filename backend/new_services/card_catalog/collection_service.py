from fastapi import  HTTPException
from backend.schemas.user_management.user import UserInDB
from backend.schemas.collections.collection import CreateCollection, UpdateCollection
from backend.dependencies.auth.users import currentActiveUser
from backend.repositories.card_catalog.collection_repository import ColletionRepository
from typing import  Optional
from backend.request_handling.StandardisedQueryResponse import ApiResponse
from backend.exceptions import card_catalog_exceptions


async def get_collection_by_id(repository: ColletionRepository, collection_id: str):
    try:
        collection = await repository.get(collection_id)
        if not collection:
            raise card_catalog_exceptions.CollectionNotFoundError(f"Collection with ID {collection_id} not found")
        return collection
    except Exception as e:
        raise card_catalog_exceptions.CollectionRetrievalError(f"Failed to retrieve collection: {str(e)}")
    
async def add(repository : ColletionRepository, created_collection : CreateCollection, user : UserInDB = currentActiveUser)->dict:
    try:
        collection_id = await repository.add(user.unique_id, created_collection)

        if not collection_id:
            raise card_catalog_exceptions.CollectionCreationError("Failed to create collection")
        collection =  await get_collection_by_id(repository, collection_id)

        if not collection or collection != created_collection.name:
            raise card_catalog_exceptions.CollectionCreationError("Collection creation did not return expected data")
    except Exception as e:
        raise card_catalog_exceptions.CollectionCreationError(f"Failed to create collection: {str(e)}")

async def get(repository: ColletionRepository, collection_id : str ,  user : UserInDB = currentActiveUser )->ApiResponse:
    try:
        collection = await repository.get(collection_id, user.unique_id)
        if not collection:
            raise card_catalog_exceptions.CollectionNotFoundError(f"Collection with ID {collection_id} not found")
    except Exception as e:
        raise card_catalog_exceptions.CollectionRetrievalError(f"Failed to retrieve collection: {str(e)}")

async def get_many(repository: ColletionRepository, user: UserInDB = currentActiveUser, collection_id : Optional[str] = None) -> ApiResponse:
    try:
        collections = await repository.get_many(user, collection_id)
        if not collections:
            return card_catalog_exceptions.CollectionNotFoundError(f"No collections found for user {user.unique_id}")
        return collections
    except Exception as e:
        raise card_catalog_exceptions.CollectionRetrievalError(f"Failed to retrieve collections: {str(e)}")

async def update_collection(repository: ColletionRepository, collection_id : str, updated_collection : UpdateCollection , user : currentActiveUser):
    update_fields = {k: v for k, v in updated_collection.model_dump(exclude_unset=True).items()}
    if not update_fields:
        raise card_catalog_exceptions.CollectionUpdateError("No fields to update")
    try:
        existing = await repository.get(collection_id)
        if not existing:
            raise card_catalog_exceptions.CollectionNotFoundError(f"Collection with ID {collection_id} not found")
            
        if str(existing.get("user_id")) != str(user.unique_id):
            raise card_catalog_exceptions.CollectionAccessDeniedError("You don't have permission to update this collection")
        
        success = await repository.update(collection_id, update_fields, user.unique_id)

        if not success:
            raise card_catalog_exceptions.CollectionUpdateError("Update operation failed")
        
        updated_entity = await repository.get(collection_id)
        return updated_entity
    except (card_catalog_exceptions.CollectionNotFoundError, card_catalog_exceptions.CollectionAccessDeniedError, card_catalog_exceptions.EmptyUpdateError) as e:
        raise
    except Exception as e:
        raise card_catalog_exceptions.CollectionUpdateError(f"Failed to update collection: {str(e)}")

async def delete_collection(repository: ColletionRepository, collection_id : str, user : UserInDB):
    try:
        await repository.delete(collection_id, user.unique_id)
    except Exception as e:
        raise card_catalog_exceptions.CollectionDeleteError(f"Failed to delete collection: {str(e)}")
    
