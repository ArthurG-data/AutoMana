from backend.modules.internal.sets.models import  UpdatedSet
from backend.database.database_utilis import execute_insert_query
from psycopg2.extensions import connection
from uuid import UUID
from backend.modules.internal.sets.models import NewSet, NewSets


def add_set(new_set : NewSet, conn: connection):
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