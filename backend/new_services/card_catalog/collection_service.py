from backend.repositories.card_catalog import collection_repository
from backend.schemas.user_management.user import UserInDB
from backend.schemas.collections.collection import CreateCollection, PublicCollection, UpdateCollection, CollectionInDB
from backend.repositories.card_catalog.collection_repository import CollectionRepository
from typing import  Optional, List
from uuid import UUID
from backend.request_handling.StandardisedQueryResponse import ApiResponse
from backend.exceptions.service_layer_exceptions.card_catalogue import card_catalog_exceptions

async def get_collection_by_id(user_collection_repository: CollectionRepository
                               , collection_id: str):
    try:
        collection = await user_collection_repository.get(collection_id)
        if not collection:
            raise card_catalog_exceptions.CollectionNotFoundError(f"Collection with ID {collection_id} not found")
        return collection
    except card_catalog_exceptions.CollectionNotFoundError:
    # Re-raise not found errors directly
        raise
    except Exception as e:
        raise card_catalog_exceptions.CollectionRetrievalError(f"Failed to retrieve collection: {str(e)}")

async def add_collection(user_collection_repository: CollectionRepository
                         , created_collection: CreateCollection
                         , user: UserInDB
                         ) -> dict:
    try:
        result = await user_collection_repository.add(created_collection.collection_name
                                                 , created_collection.description
                                                 , user.unique_id)
        print(f"Collection created with result: {result}")
        if not result:
            raise card_catalog_exceptions.CollectionCreationError("Failed to create collection")
        return result
    except card_catalog_exceptions.CollectionCreationError:
        raise
    except Exception as e:
        raise card_catalog_exceptions.CollectionCreationError(f"Failed to create collection: {str(e)}")

async def get_collection(user_collection_repository: CollectionRepository, collection_id: str, user : UserInDB) -> PublicCollection:
    try:
        collection = await user_collection_repository.get(collection_id, user.unique_id)
        if collection is None:
            raise card_catalog_exceptions.CollectionNotFoundError(f"Collection with ID {collection_id} not found")
        return PublicCollection.model_validate(collection)
    except card_catalog_exceptions.CollectionNotFoundError:
        raise
    except card_catalog_exceptions.CollectionAccessDeniedError:
        raise
    except Exception as e:
        raise card_catalog_exceptions.CollectionRetrievalError(f"Failed to retrieve collection: {str(e)}")

async def get_all_collections(user_collection_repository: CollectionRepository, user_id: UUID) -> List[CollectionInDB]:
    """Get all collections for a user"""
    try:
        collections = await user_collection_repository.get_all(user_id)
        if not collections or len(collections) == 0:
            raise card_catalog_exceptions.CollectionNotFoundError(f"No collections found for user {user_id}")
        return [CollectionInDB.model_validate(c) for c in collections]
    except card_catalog_exceptions.CollectionNotFoundError:
        raise
    except Exception as e:
        raise card_catalog_exceptions.CollectionRetrievalError(f"Failed to retrieve collections: {str(e)}")

async def get_many(user_collection_repository: CollectionRepository, user_id: UUID, collection_id: List[UUID]) -> List[CollectionInDB]:
    try:
        collections = await user_collection_repository.get_many(user_id, collection_id)
        if not collections or collections == []:
            raise card_catalog_exceptions.CollectionNotFoundError(f"No collections found for user {user_id}")
        return [CollectionInDB.model_validate(c) for c in collections]
    except card_catalog_exceptions.CollectionNotFoundError:
        raise
    except Exception as e:
        raise card_catalog_exceptions.CollectionRetrievalError(f"Failed to retrieve collections: {str(e)}")

async def update_collection(user_collection_repository: CollectionRepository
                            , collection_id : UUID
                            , updated_collection: UpdateCollection, 
                            user : UserInDB):
    update_fields = {k: v for k, v in updated_collection.model_dump(exclude_unset=True).items()}
    if not update_fields:
        raise card_catalog_exceptions.CollectionUpdateError("No fields to update")
    try:
        await user_collection_repository.update(update_fields, collection_id, user.unique_id)
        return 
    except (card_catalog_exceptions.CollectionNotFoundError, card_catalog_exceptions.CollectionAccessDeniedError, card_catalog_exceptions.EmptyUpdateError) as e:
        raise
    except Exception as e:
        raise card_catalog_exceptions.CollectionUpdateError(f"Failed to update collection: {str(e)}")

async def delete_collection(user_collection_repository: CollectionRepository
                            , collection_id: UUID
                            , user: UserInDB
                            ) -> bool:
    try:
        await user_collection_repository.delete(collection_id, user.unique_id)

        check = await user_collection_repository.get(collection_id, user.unique_id)
        if check:
            raise card_catalog_exceptions.CollectionDeleteError(f"Collection with ID {collection_id} was not deleted successfully")
        return True     
    except card_catalog_exceptions.CollectionNotFoundError:
        raise
    except Exception as e:
        raise card_catalog_exceptions.CollectionDeleteError(f"Failed to delete collection: {str(e)}")
    
