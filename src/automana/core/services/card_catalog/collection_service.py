from automana.core.repositories.card_catalog import collection_repository
from automana.api.schemas.user_management.user import UserInDB
from automana.core.models.collections.collection import (
    CreateCollection, PublicCollection, UpdateCollection, CollectionInDB,
    AddCollectionEntryRequest, PublicCollectionEntry,
)
from automana.core.repositories.card_catalog.collection_repository import CollectionRepository
from automana.core.repositories.card_catalog.card_repository import CardReferenceRepository
from typing import Optional, List
from uuid import UUID
from automana.core.exceptions.service_layer_exceptions.card_catalogue import card_catalog_exceptions
from automana.core.service_registry import ServiceRegistry
import logging

logger = logging.getLogger(__name__)

@ServiceRegistry.register(
    "card_catalog.collection.add",
    db_repositories=["user_collection"]
)
async def add_collection(user_collection_repository: CollectionRepository
                         , created_collection: CreateCollection
                         , user: UserInDB
                         ) -> dict:
    try:
        result = await user_collection_repository.add(created_collection.collection_name
                                                 , created_collection.description
                                                 , user.unique_id)
        if not result:
            raise card_catalog_exceptions.CollectionCreationError("Failed to create collection")
        return result
    except card_catalog_exceptions.CollectionCreationError:
        raise
    except Exception as e:
        raise card_catalog_exceptions.CollectionCreationError(f"Failed to create collection: {str(e)}")


@ServiceRegistry.register(
    "card_catalog.collection.get",
    db_repositories=["user_collection"]
)
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


@ServiceRegistry.register(
    "card_catalog.collection.get_all",
    db_repositories=["user_collection"]
)
async def get_all_collections(user_collection_repository: CollectionRepository, user_id: UUID) -> List[CollectionInDB]:
    """Get all collections for a user"""
    try:
        collections = await user_collection_repository.get_all(user_id)
        if not collections:
            return []
        return [CollectionInDB.model_validate(c) for c in collections]
    except Exception as e:
        raise card_catalog_exceptions.CollectionRetrievalError(f"Failed to retrieve collections: {str(e)}")


@ServiceRegistry.register(
    "card_catalog.collection.get_many",
    db_repositories=["user_collection"]
)
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


@ServiceRegistry.register(
    "card_catalog.collection.update",
    db_repositories=["user_collection"]
)
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


@ServiceRegistry.register(
    "card_catalog.collection.delete",
    db_repositories=["user_collection"]
)
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
    


# Finish code → finish_id lookup (pricing.card_finished)
_FINISH_CODE_TO_ID = {"NONFOIL": 1, "FOIL": 2, "ETCHED": 3}


@ServiceRegistry.register(
    "card_catalog.collection.add_entry",
    db_repositories=["user_collection", "card"]
)
async def add_entry(
    user_collection_repository: CollectionRepository,
    card_repository: CardReferenceRepository,
    collection_id: UUID,
    user: UserInDB,
    request: AddCollectionEntryRequest,
) -> PublicCollectionEntry:
    # 1. Resolve card_version_id
    if request.card_version_id:
        card_version_id = request.card_version_id
    elif request.scryfall_id:
        row = await card_repository.get_version_by_scryfall_id(request.scryfall_id)
        if not row:
            raise card_catalog_exceptions.CollectionCreationError(
                f"No card found for scryfall_id={request.scryfall_id}"
            )
        card_version_id = row["card_version_id"]
    else:
        row = await card_repository.get_version_by_set_collector(
            request.set_code, request.collector_number
        )
        if not row:
            raise card_catalog_exceptions.CollectionCreationError(
                f"No card found for {request.set_code}/{request.collector_number}"
            )
        card_version_id = row["card_version_id"]

    # 2. Verify collection belongs to user
    col = await user_collection_repository.get(collection_id, user.unique_id)
    if not col:
        raise card_catalog_exceptions.CollectionNotFoundError(
            f"Collection {collection_id} not found"
        )

    # 3. Resolve finish_id
    finish_id = _FINISH_CODE_TO_ID.get(request.finish.value)
    if finish_id is None:
        raise card_catalog_exceptions.CollectionCreationError(
            f"Unknown finish: {request.finish}"
        )

    # 4. Insert
    row = await user_collection_repository.add_entry(
        collection_id=collection_id,
        user_id=user.unique_id,
        card_version_id=card_version_id,
        finish_id=finish_id,
        condition=request.condition.value,
        purchase_price=request.purchase_price,
        currency_code=request.currency_code,
        purchase_date=request.purchase_date,
        language_id=request.language_id,
    )
    if not row:
        raise card_catalog_exceptions.CollectionCreationError("Failed to insert entry")

    entry = await user_collection_repository.get_entry(
        row["item_id"], collection_id, user.unique_id
    )
    return PublicCollectionEntry.model_validate(entry)


@ServiceRegistry.register(
    "card_catalog.collection.list_entries",
    db_repositories=["user_collection"]
)
async def list_entries(
    user_collection_repository: CollectionRepository,
    collection_id: UUID,
    user: UserInDB,
) -> List[PublicCollectionEntry]:
    col = await user_collection_repository.get(collection_id, user.unique_id)
    if not col:
        raise card_catalog_exceptions.CollectionNotFoundError(
            f"Collection {collection_id} not found"
        )
    rows = await user_collection_repository.get_all_entries(collection_id, user.unique_id)
    return [PublicCollectionEntry.model_validate(r) for r in rows]


@ServiceRegistry.register(
    "card_catalog.collection.get_entry",
    db_repositories=["user_collection"]
)
async def get_entry(
    user_collection_repository: CollectionRepository,
    collection_id: UUID,
    entry_id: UUID,
    user: UserInDB,
) -> PublicCollectionEntry:
    row = await user_collection_repository.get_entry(entry_id, collection_id, user.unique_id)
    if not row:
        raise card_catalog_exceptions.CollectionNotFoundError(
            f"Entry {entry_id} not found"
        )
    return PublicCollectionEntry.model_validate(row)


@ServiceRegistry.register(
    "card_catalog.collection.delete_entry",
    db_repositories=["user_collection"]
)
async def delete_entry(
    user_collection_repository: CollectionRepository,
    collection_id: UUID,
    entry_id: UUID,
    user: UserInDB,
) -> None:
    deleted = await user_collection_repository.delete_entry(entry_id, collection_id, user.unique_id)
    if not deleted:
        raise card_catalog_exceptions.CollectionNotFoundError(
            f"Entry {entry_id} not found"
        )
