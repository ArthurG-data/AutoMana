## this script will introspect database schemas and return useful information about them, such as tables, columns and relationships.
import json
from sqlalchemy import inspect, text
from typing import List, Optional
import sys
from pathlib import Path
from dataclasses import dataclass, asdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from  connection import get_connection, get_engine

@dataclass
class table_entry:
    db_name: str
    schema_name: str
    table_name: str
    row_count: int
    description: Optional[str]



@dataclass
class column_entry:
    db_name: str
    table_name : str
    schema_name : Optional[str]
    column_name: str
    data_type: str
    is_nullable: bool
    is_pk: bool
    description: Optional[str]

@dataclass
class relationship_entry:
    from_db_name: str
    from_schema_name: Optional[str]
    from_table_name: str
    from_column: str
    to_db_name: str
    to_schema_name: Optional[str]
    to_table_name: str
    to_column: str
    relationship_type: str

@dataclass
class Entity:
    entity_type_name: str
    db_name: str
    schema_name: Optional[str]
    object_name: str
    parent_entity_name: Optional[str]

@dataclass
class Attribute:
    entity_name: str
    attribute_key: str
    attribute_value: str

def introspect_schemas(engine, schemas: List[str]) -> tuple:
    """ Introspect the database schemas and return entities and attributes """
    entities_list = []
    attributes_list = []
    relationships_list = []

    insp = inspect(engine)
    
    for schema in schemas:
        print(f"Introspecting schema: {schema}")
        
        # Create schema entity
        schema_entity = Entity(
            entity_type_name='schema',
            db_name=engine.url.database,
            schema_name=schema,
            object_name=schema,
            parent_entity_name=None
        )
        entities_list.append(schema_entity)
        
        tables = insp.get_table_names(schema=schema)
        
        for table_name in tables:
            print(f"  Introspecting table: {table_name}")
            
            with engine.connect() as conn:
                row_count = conn.execute(text(
                    "SELECT reltuples::bigint FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE c.relname = :name AND n.nspname = :schema"
                ), {"name": table_name, "schema": schema}).scalar()
                
                description = conn.execute(text("""
                    SELECT d.description 
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    LEFT JOIN pg_description d ON d.objoid = c.oid AND d.objsubid = 0
                    WHERE c.relname = :table AND n.nspname = :schema
                """), {"schema": schema, "table": table_name}).scalar()
            
            # Table entity
            table_entity = Entity(
                entity_type_name='table',
                db_name=engine.url.database,
                schema_name=schema,
                object_name=table_name,
                parent_entity_name=schema
            )
            entities_list.append(table_entity)
            
            # Table attributes
            table_id = f"{engine.url.database}.{schema}.{table_name}"
            if row_count is not None:
                attributes_list.append(Attribute(
                    entity_name=table_id,
                    attribute_key="row_count",
                    attribute_value=str(row_count)
                ))
            if description:
                attributes_list.append(Attribute(
                    entity_name=table_id,
                    attribute_key="description",
                    attribute_value=description
                ))
            
            # Foreign keys
            with engine.connect() as conn:
                fk_check = conn.execute(text("""
                    SELECT
                        tc.constraint_name,
                        kcu.column_name,
                        ccu.table_schema AS foreign_table_schema,
                        ccu.table_name AS foreign_table_name,
                        ccu.column_name AS foreign_column_name
                    FROM information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu
                      ON tc.constraint_name = kcu.constraint_name
                      AND tc.table_schema = kcu.table_schema
                    JOIN information_schema.constraint_column_usage AS ccu
                      ON ccu.constraint_name = tc.constraint_name
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                      AND tc.table_schema = :schema
                      AND tc.table_name = :table
                """), {"schema": schema, "table": table_name}).fetchall()
            
            for fk_row in fk_check:
                relationships_list.append(relationship_entry(
                    from_db_name=engine.url.database,
                    from_schema_name=schema,
                    from_table_name=table_name,
                    from_column=fk_row.column_name,
                    to_db_name=engine.url.database,
                    to_schema_name=fk_row.foreign_table_schema,
                    to_table_name=fk_row.foreign_table_name,
                    to_column=fk_row.foreign_column_name,
                    relationship_type='foreign_key'
                ))
            
            # Columns
            columns = insp.get_columns(table_name, schema=schema)
            pk_constraint = insp.get_pk_constraint(table_name, schema=schema)
            pk_columns = pk_constraint.get('constrained_columns', []) if pk_constraint else []
            
            for col in columns:
                column_entity = Entity(
                    entity_type_name='column',
                    db_name=engine.url.database,
                    schema_name=schema,
                    object_name=col['name'],
                    parent_entity_name=table_name
                )
                entities_list.append(column_entity)
                
                column_id = f"{engine.url.database}.{schema}.{table_name}.{col['name']}"
                attributes_list.extend([
                    Attribute(column_id, "data_type", str(col['type'])),
                    Attribute(column_id, "is_nullable", str(col['nullable'])),
                    Attribute(column_id, "is_pk", str(col['name'] in pk_columns)),
                    Attribute(column_id, "table_name", table_name)
                ])
    
    return (
        [asdict(e) for e in entities_list],
        [asdict(a) for a in attributes_list],
        [asdict(r) for r in relationships_list]
    )

if __name__ == "__main__":
    engine = get_engine()
    schemas = ['ops', 'markets', 'public']
    entities_list, attributes_list, relationships_list = introspect_schemas(engine, schemas)
    print(entities_list[:5])
    print(attributes_list[:5])
    print(relationships_list[:5])

    with engine.begin() as conn:
        conn.execute(
            text("""
                SELECT sql_agent_metadata.insert_raw_metadata(
                    CAST(:entities AS jsonb),
                    CAST(:attributes AS jsonb)
                );
            """),
            {
                "entities": json.dumps(entities_list),
                "attributes": json.dumps(attributes_list),
            }
        )


