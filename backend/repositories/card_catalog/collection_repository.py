from typing import Optional, List
from uuid import UUID
from backend.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository
from backend.schemas.collections.collection import CreateCollection
from backend.schemas.user_management.user import UserInDB

class CollectionRepository(AbstractRepository):
    def __init__(self, connection, executor = None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "CollectionRepository"
    
    async def get(self, collection_id: UUID, user_id: UUID) -> Optional[dict]:
        query = """ SELECT u.username, c.description, c.collection_name, c.is_active 
                    FROM user_collection.collections c JOIN user_management.users u 
                    ON c.user_id = u.unique_id 
                    WHERE c.user_id = $1
                    AND c.is_active = True
                    AND c.collection_id =  $2;"""
        result = await self.execute_query(query, (user_id, collection_id))
        return result[0] if result else None

    async def add(self
                  , collection_name:str
                  , description: str
                  , user_id: UUID) -> Optional[UUID]:
        query = "INSERT INTO user_collection.collections (collection_name, description, user_id) VALUES ($1, $2, $3)  RETURNING collection_id ;"
        result =await self.execute_command(query, (collection_name, description, user_id))
        return result[0] if result else None

    async def add_many(self, values: List[CreateCollection]):
        query = "INSERT INTO user_collection.collections (collection_name, description, user_id) VALUES ($1, $2, $3)  RETURNING collection_id"
        return await self.execute_command(query, (values.collection_name, values.description,    values.user_id))

    async def get_all(self, user_id: UUID) -> List[dict]:
        query = """ SELECT u.username, c.collection_name, c.is_active 
                    FROM user_collection.collections c JOIN user_management.users u 
                    ON c.user_id = u.unique_id 
                    WHERE c.user_id = $1 AND c.is_active = True;"""
        return await self.execute_query(query, user_id)
    
    async def get_many(self, user,  collection_id :List[UUID]):
        counter = 1
        query = f""" SELECT u.username, c.collection_name, c.is_active 
                    FROM user_collection.collections c JOIN user_management.users u 
                    ON c.user_id = u.unique_id 
                    WHERE c.user_id = ${counter} AND c.is_active = True AND c.collection_id IN ({', '.join([f'${counter + i}' for i in range(len(collection_id))])});"""
        values= (user.unique_id, *collection_id)
        return await self.execute_query( query, values=values)
   
        
    async def delete(self, collection_id : UUID, user_id : UUID):
        query = "UPDATE user_collection.collections set is_active = False WHERE collection_id = $1 AND user_id = $2;"
        return await self.execute_command(query, (collection_id, user_id))

    async def delete_many(self, collection_ids: List[UUID], user_id: UUID):
        query = "UPDATE user_collection.collections SET is_active = False WHERE collection_id IN ($1) AND user_id = $2;"
        return self.execute_command(query, (collection_ids, user_id))
    
    async def update(self, update_fields, collection_id, user_id):
        counter = 1
        query = "UPDATE user_collection.collections SET " + ", ".join(f"{k} = ${counter + i}" for i, k in enumerate(update_fields.keys())) + f" WHERE collection_id = ${counter + len(update_fields)} AND user_id =${counter+len(update_fields)+1}"
        values = (*update_fields.values(), collection_id, user_id)
        print(values)
        return await self.execute_command(query, values)

    async def list():
        raise NotImplementedError("This method is not implemented yet")

