from typing import List,  Optional
from uuid import UUID
from backend.repositories.card_catalog.set_repository import SetReferenceRepository
from backend.schemas.card_catalog.set import  SetInDB, NewSet, UpdatedSet, NewSets
from backend.exceptions.service_layer_exceptions.card_catalogue import set_exception
from backend.shared.utils import decode_json_input

async def get(set_repository: SetReferenceRepository
              , set_id: UUID) -> SetInDB:
    try:
        result = await set_repository.get(set_id)
        if not result:
            raise set_exception.SetNotFoundError(f"Set with ID {set_id} not found")
        return SetInDB.model_validate(result)
    except set_exception.SetNotFoundError:
        raise
    except Exception as e:
        raise set_exception.SetRetrievalError(f"Failed to retrieve set: {str(e)}")

async def get_all(set_repository: SetReferenceRepository
                  ,limit: Optional[int] = None
                  ,offset: Optional[int] = None
                  ,ids: Optional[List[UUID]] = None
                  ) -> List[SetInDB]:
    try:
        results = await set_repository.list(limit=limit, offset=offset, ids=ids)
        if not results:
            raise set_exception.SetNotFoundError("No sets found")
        return [SetInDB.model_validate(result) for result in results]
    except set_exception.SetNotFoundError:
        raise
    except Exception as e:
        raise set_exception.SetRetrievalError(f"Failed to retrieve sets: {str(e)}")

async def add_set(set_repository: SetReferenceRepository, new_set: NewSet) -> SetInDB:
    data = new_set.create_values()
    #values = tuple(v for _, v in data.items())
    try:
        result = await set_repository.add(data)
        if not result:
            raise set_exception.SetCreationError("Failed to create set")
        return SetInDB .model_validate(result)
    except set_exception.SetCreationError:
        raise
    

async def add_sets_bulk(set_repository: SetReferenceRepository, new_sets: NewSets) -> List[SetInDB]:
    """ Adds multiple sets to the database in a single transaction."""
    data = [set.create_values() for set in new_sets]
    try:
        results = await set_repository.add_many(data)
        if not results or len(results) == 0:
            raise set_exception.SetCreationError("Failed to create sets")
        return [SetInDB.model_validate(result) for result in results]
    except set_exception.SetCreationError:
        raise
    except Exception as e:
        raise set_exception.SetCreationError(f"Failed to create sets: {str(e)}")

async def put_set(set_repository: SetReferenceRepository, set_id: UUID, update_set: UpdatedSet):
    try:
        not_nul = {k: v for k, v in update_set.model_dump().items() if v is not None}
        if not_nul == {}:
            raise set_exception.SetUpdateError("No fields to update")

        result = await set_repository.update(set_id, not_nul)
        if not result:
            raise set_exception.SetNotFoundError(f"Failed to update set with ID {set_id}")
        return SetInDB.model_validate(result)
    except set_exception.SetNotFoundError:
        raise
    except Exception as e:
        raise set_exception.SetUpdateError(f"Failed to update set: {str(e)}")


async def get_parsed_set(file_content : bytes)-> NewSets:
    """Dependency that parses sets from an uploaded JSON file."""
    try:
        data =  await decode_json_input(file_content)
        return NewSets(items = data)
    except Exception as e:
        raise set_exception.SetParsingError(f"Failed to parse sets from JSON: {str(e)}") 

    