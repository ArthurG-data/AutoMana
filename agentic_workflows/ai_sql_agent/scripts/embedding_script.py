import json
from xmlrpc import client
from sqlalchemy import inspect, text
from typing import List, Optional
import sys
from pathlib import Path
from dataclasses import dataclass, asdict
from openai import OpenAI
from sqlalchemy.orm import sessionmaker
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from  connection import get_connection, get_engine

def generate_embedding(text: str, model: str = "text-embedding-3-small") -> List[float]:
    """Generate embedding for given text using OpenAI"""
    response = client.embeddings.create(
        input=text,
        model=model
    )
    return response.data[0].embedding

def create_entity_description(entity_type: str, entity: dict, attributes: dict) -> tuple:
    """Create a text description for an entity based on its type and attributes"""
    
    db_name = entity['db_name']
    schema_name = entity['schema_name']
    object_name = entity['object_name']
    
    if entity_type == 'schema':
        name = f"{db_name}.{schema_name}"
        description = f"Database schema '{schema_name}' in database '{db_name}'."
        
    elif entity_type == 'table':
        name = f"{schema_name}.{object_name}"
        row_count = attributes.get('row_count', 'unknown')
        desc = attributes.get('description', '')
        description = f"Table '{object_name}' in schema '{schema_name}'. Row count: {row_count}. {desc}"
        
    elif entity_type == 'column':
        table_name = attributes.get('table_name', '')
        data_type = attributes.get('data_type', '')
        is_pk = attributes.get('is_pk', 'False')
        is_nullable = attributes.get('is_nullable', 'True')
        
        name = f"{schema_name}.{table_name}.{object_name}"
        pk_text = " PRIMARY KEY." if is_pk == 'True' else ""
        null_text = " NOT NULL." if is_nullable == 'False' else " NULLABLE."
        description = f"Column '{object_name}' in table '{schema_name}.{table_name}'. Type: {data_type}.{pk_text}{null_text}"
    
    else:
        name = object_name
        description = f"Entity '{object_name}' of type '{entity_type}'."
    
    return name, description

def generate_embeddings_for_entities(engine, embedding_model: str = "text-embedding-3-small"):
    """Generate and store embeddings for all entities"""
    
    with engine.begin() as conn:
        # Get all entities with their attributes
        entities = conn.execute(text("""
            SELECT 
                e.id,
                e.entity_type_id,
                o.object_type,
                e.db_name,
                e.schema_name,
                e.object_name,
                e.parent_entity_id
            FROM sql_agent_metadata.entity e
            JOIN sql_agent_metadata.object_ref o ON o.id = e.entity_type_id
            ORDER BY e.entity_type_id, e.id
        """)).fetchall()
        
        print(f"Processing {len(entities)} entities...")
        
        for idx, entity in enumerate(entities, 1):
            entity_id = entity.id
            entity_type = entity.object_type
            
            # Get attributes for this entity
            attrs = conn.execute(text("""
                SELECT attribute_key, attribute_value
                FROM sql_agent_metadata.entity_attribute
                WHERE entity_id = :entity_id
            """), {"entity_id": entity_id}).fetchall()
            
            attributes = {attr.attribute_key: attr.attribute_value for attr in attrs}
            
            # Create description
            entity_dict = {
                'db_name': entity.db_name,
                'schema_name': entity.schema_name,
                'object_name': entity.object_name
            }
            
            name, description = create_entity_description(entity_type, entity_dict, attributes)
            
            print(f"[{idx}/{len(entities)}] Generating embedding for {entity_type}: {name}")
            
            # Generate embedding
            try:
                embedding = generate_embedding(description, embedding_model)
                
                # Insert into schema_embeddings
                conn.execute(text("""
                    INSERT INTO sql_agent_metadata.schema_embeddings
                        (object_id, name, description, embedding, embedding_model)
                    VALUES (:object_id, :name, :description, :embedding, :model)
                    ON CONFLICT (object_id, embedding_model)
                    DO UPDATE SET
                        name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        embedding = EXCLUDED.embedding,
                        updated_at = now()
                """), {
                    "object_id": entity_id,
                    "name": name,
                    "description": description,
                    "embedding": str(embedding),  # PostgreSQL will cast this
                    "model": embedding_model
                })
            except Exception as e:
                print(f"Error processing entity {entity_id}: {e}")
                continue
        
        print(f"\nSuccessfully generated embeddings for {len(entities)} entities!")


if __name__ == "__main__":
    engine = get_engine()
    client = OpenAI()
    SessionLocal = sessionmaker(bind=engine)
    generate_embeddings_for_entities(engine)