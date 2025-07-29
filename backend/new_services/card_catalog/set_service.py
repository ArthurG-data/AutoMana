from typing import List,  Optional
from uuid import UUID
from backend.utils_new.card_catalog import create_value_set
from backend.utils_new.card_catalog.create_value_set import create_value
from backend.repositories.card_catalog.set_repository import SetReferenceRepository
from backend.schemas.card_catalog.set import BaseSet, SetInDB, NewSet, UpdatedSet
from backend.exceptions.card_catalogue import set_exception

async def get(repository: SetReferenceRepository, set_id: UUID) -> SetInDB:
    try:
        result = await repository.get(set_id)
        if not result:
            raise set_exception.SetNotFoundError(f"Set with ID {set_id} not found")
        return SetInDB.model_validate(result[0])
    except set_exception.SetNotFoundError:
        raise
    except Exception as e:
        raise set_exception.SetRetrievalError(f"Failed to retrieve set: {str(e)}")

async def list(repository: SetReferenceRepository, limit : Optional[int]=None, offset : Optional[int]=None, ids : Optional[List[UUID]]=None) ->  List[SetInDB]:
    results = await repository.list(limit=limit, offset=offset, ids=ids)
    sets = [SetInDB.model_validate(result) for result in results]
    return sets

def add_set(repository: SetReferenceRepository, new_set : NewSet):
    query = "SELECT insert_joined_set (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
    data = new_set.model_dump()
    #values = tuple(v for _, v in data.items())
    values = (
        data["id"],
        data["name"],
        data["code"],
        data["set_type"],
        data["released_at"],
        data["digital"],
        data["nonfoil_only"],
        data["foil_only"],
        data["parent_set_code"],
        data["icon_svg_uri"]
    )
    execute_insert_query(conn, query, values)
    

def add_sets_bulk(new_sets : NewSets, conn: connection):
    query = "SELECT insert_joined_set (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
    values_list = []
    for item in new_sets.items:
        data = item.model_dump()
        values = tuple(v for _, v in data.items())
        values_list.append(values)
    return execute_insert_query(conn, query, values_list, execute_many=True)
    
def put_set(conn: connection, set_id : UUID, update_set : UpdatedSet):
    not_nul = [k for k,v in update_set.model_dump().items() if v != None]
    update_string = ', '.join([f'{update} = %s'for update in not_nul])
    query = """WITH """
    params = []
    if 'set_type' in not_nul:
        query +=  """ins_set_type AS (
                INSERT INTO set_type_list_ref (set_type)
                VALUES (%s)
                ON CONFLICT DO NOTHING
                RETURNING set_type_id
                ),
                get_set_type AS (
                SELECT set_type_id FROM ins_set_type
                UNION
                SELECT set_type_id FROM set_type_list_ref WHERE set_type = %s
                ),"""
    params.extend([update_set.set_type] * 2)
    if 'foil_status_id' in not_nul:
        query +=  """ins_foil_ref AS ( 
                INSERT INTO foil_status_ref (foil_status_desc)
                VALUES (%s)
                ON CONFLICT DO NOTHING
                RETURNING foil_status_id
                ),
                get_foil_ref AS (
                SELECT foil_status_id FROM ins_foil_ref 
                UNION
                SELECT foil_status_id FROM foil_status_ref WHERE foil_status_desc = %s
                ), """
    if 'parent_set' in not_nul:
         query += """get_parent_set AS (
                    SELECT set_id from sets
                    WHERE set_name = %s     
                    ),
                  """
    query += f" UPDATE sets SET ({update_string}) WHERE set_id = %s"
    params.extend([update_set.foil_status_id] * 2)
    for entry in not_nul:
        if entry not in ['foil_status_id', 'set_type']:
            params.append(getattr(update_set, entry, None))
    params.append(set_id)
    try:
        execute_insert_query(conn, query, params)
    except Exception:
        raise


async def get_parsed_set(file: UploadFile = File(...))-> NewSets:
    """Dependency that parses sets from an uploaded JSON file."""
    try:
        return await sets_from_json(file)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid set JSON: {str(e)}")

    