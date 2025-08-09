from backend.schemas.user_management.user import UserInDB
from backend.schemas.collections.collection import CreateCollection, UpdateCollection, CollectionInDB
from backend.repositories.card_catalog.collection_repository import ColletionRepository
from typing import  Optional, List
from uuid import UUID
from backend.request_handling.StandardisedQueryResponse import ApiResponse
from backend.exceptions.service_layer_exceptions.card_catalogue import card_catalog_exceptions

async def get_collection_by_id(repository: ColletionRepository, collection_id: str):
    try:
        collection = await repository.get(collection_id)
        if not collection:
            raise card_catalog_exceptions.CollectionNotFoundError(f"Collection with ID {collection_id} not found")
        return collection
    except card_catalog_exceptions.CollectionNotFoundError:
    # Re-raise not found errors directly
        raise
    except Exception as e:
        raise card_catalog_exceptions.CollectionRetrievalError(f"Failed to retrieve collection: {str(e)}")
    
async def add(repository : ColletionRepository, created_collection : CreateCollection)->CollectionInDB:
    try:
        result = await repository.add(created_collection.collection_name, created_collection.user_id)

        if not result:
            raise card_catalog_exceptions.CollectionCreationError("Failed to create collection")
        if result['collection_name'] != created_collection.collection_name:
            raise card_catalog_exceptions.CollectionCreationError(f"Collection creation did not return expected data. Expected collection name: {created_collection.collection_name}, got: {result['collection_name']}")
        return CollectionInDB.model_validate(result)
    except card_catalog_exceptions.CollectionCreationError:
        raise
    except Exception as e:
        raise card_catalog_exceptions.CollectionCreationError(f"Failed to create collection: {str(e)}")

async def get(repository: ColletionRepository, collection_id : str ,  user_id: UUID) -> CollectionInDB:
    try:
        collection = await repository.get(collection_id, user_id)
        if collection is None:
            raise card_catalog_exceptions.CollectionNotFoundError(f"Collection with ID {collection_id} not found")
        if collection.get("user_id") != str(user_id):
            raise card_catalog_exceptions.CollectionAccessDeniedError("You don't have permission to access this collection")
        return CollectionInDB.model_validate(collection)
    except card_catalog_exceptions.CollectionNotFoundError:
        raise
    except card_catalog_exceptions.CollectionAccessDeniedError:
        raise
    except Exception as e:
        raise card_catalog_exceptions.CollectionRetrievalError(f"Failed to retrieve collection: {str(e)}")

async def get_all_collections(repository: ColletionRepository, user_id: UUID) -> List[CollectionInDB]:
    """Get all collections for a user"""
    try:
        collections = await repository.get_all(user_id)
        if not collections or len(collections) == 0:
            raise card_catalog_exceptions.CollectionNotFoundError(f"No collections found for user {user_id}")
        return [CollectionInDB.model_validate(c) for c in collections]
    except card_catalog_exceptions.CollectionNotFoundError:
        raise
    except Exception as e:
        raise card_catalog_exceptions.CollectionRetrievalError(f"Failed to retrieve collections: {str(e)}")
    
async def get_many(repository: ColletionRepository, user_id: UUID , collection_id : List[UUID]) -> List[CollectionInDB]:
    try:
        collections = await repository.get_many(user_id, collection_id)
        if not collections or collections == []:
            raise card_catalog_exceptions.CollectionNotFoundError(f"No collections found for user {user_id}")
        return [CollectionInDB.model_validate(c) for c in collections]
    except card_catalog_exceptions.CollectionNotFoundError:
        raise
    except Exception as e:
        raise card_catalog_exceptions.CollectionRetrievalError(f"Failed to retrieve collections: {str(e)}")

async def update_collection(repository: ColletionRepository, updated_collection : UpdateCollection):
    raise NotImplementedError("This function is not implemented yet")
    update_fields = {k: v for k, v in updated_collection.model_dump(exclude_unset=True).items()}
    if not update_fields:
        raise card_catalog_exceptions.CollectionUpdateError("No fields to update")
    try:
      
        updated = await repository.update(updated_collection.collection_id, update_fields, updated_collection.user_id)
        updated_entity = await repository.get(updated_collection.collection_id)
        return updated_entity
    except (card_catalog_exceptions.CollectionNotFoundError, card_catalog_exceptions.CollectionAccessDeniedError, card_catalog_exceptions.EmptyUpdateError) as e:
        raise
    except Exception as e:
        raise card_catalog_exceptions.CollectionUpdateError(f"Failed to update collection: {str(e)}")

async def delete_collection(repository: ColletionRepository, collection_id : str, user_id: UUID)-> bool:
    try:
        result = await repository.delete(collection_id, user_id)
        if result is None:
            raise card_catalog_exceptions.CollectionDeleteError(f"Collection with ID {collection_id} not found or could not be deleted")
        check = await repository.get(collection_id, user_id)
        if check:
            raise card_catalog_exceptions.CollectionDeleteError(f"Collection with ID {collection_id} was not deleted successfully")
        return result
    except card_catalog_exceptions.CollectionNotFoundError:
        raise
    except Exception as e:
        raise card_catalog_exceptions.CollectionDeleteError(f"Failed to delete collection: {str(e)}")
    
