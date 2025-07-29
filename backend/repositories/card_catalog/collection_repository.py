from typing import Optional, List
from uuid import UUID
from backend.repositories.AbstractRepository import AbstractRepository
from backend.schemas.collections.collection import CreateCollection
from backend.schemas.user_management.user import UserInDB

class ColletionRepository(AbstractRepository):
    def __init__(self, connection, executor = None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "CollectionRepository"
    
    async def get(self, collection_id: str, user: UserInDB):
        query = """ SELECT u.username, c.collection_name, c.is_active 
                    FROM collections c JOIN users u 
                    ON c.user_id = u.unique_id 
                    WHERE c.user_id = $1
                    AND c.is_active = True
                    AND c.collection_id =  $2;"""
        return await self.execute_query(query, (user.unique_id, collection_id))
    
    async def add(self, collection_name:str, user_id: UUID) -> Optional[str]:
        query = "INSERT INTO collections (collection_name, user_id) VALUES ($1, $2)  RETURNING collection_id"
        return await self.execute_command(query, (collection_name, user_id))
        
    async def add_many(self, values: List[CreateCollection]):
        query = "INSERT INTO collections (collection_name, user_id) VALUES ($1, $2)  RETURNING collection_id"
        return await self.execute_command(query, (values.collection_name, values.user_id))

    async def get_all(self, user_id: UUID) -> List[dict]:
        query = """ SELECT u.username, c.collection_name, c.is_active 
                    FROM collections c JOIN users u 
                    ON c.user_id = u.unique_id 
                    WHERE c.user_id = $1 AND c.is_active = True;"""
        return await self.execute_query(query, user_id)
    
    async def get_many(self, user,  collection_id :List[UUID]):
        counter = 1
        query = f""" SELECT u.username, c.collection_name, c.is_active 
                    FROM collections c JOIN users u 
                    ON c.user_id = u.unique_id 
                    WHERE c.user_id = ${counter} AND c.is_active = True AND c.collection_id IN ({', '.join([f'${counter + i}' for i in range(len(collection_id))])});"""
        values= (user.unique_id, *collection_id)
        return await self.execute_query( query, values=values)
   
        
    async def delete(self, collection_id : str, user_id : UUID):
        query = "UPDATE collections set is_active = False WHERE collection_id = $1 AND user_id = $2"
        return self.execute_command(query, (collection_id, user_id))
       
    async def delete_many():
        pass
    async def update(self, update_fields):
        counter = 1
        query = "UPDATE collections SET " + ", ".join(f"{k} = ${counter + i}" for i, k in enumerate(update_fields.keys())) + " WHERE collection_id = $1 AND user_id = $2"
        pass

