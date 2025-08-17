from pydantic import BaseModel, Field
import datetime
from uuid import UUID
from typing import Optional, List

class BaseSet(BaseModel):
  
    set_name : str=Field(
        title='The complete name of the set'
    )
    set_code : str =Field(
        title='The set symbols'
    )

class SetInDB(BaseSet):
    set_id : UUID=Field(
    title='The id in the database'
)
    set_type : str = Field(
    title='The type of set'
)

  
    digital : bool = Field(
        title='Is the set a digital only release'
)

    released_at : datetime.date = Field(
        tile = 'The released date of the set'
)


class NewSet(BaseModel):
    set_id : UUID
    set_name : str=Field(max_length=100)
    set_code : str=Field(max_length=10)
    set_type : str=Field(max_length=30)
    released_at : datetime.date
    digital : bool=Field(default=False)
    nonfoil_only : bool=Field(default=False)
    foil_only : bool=Field(default=False)
    parent_set : Optional[str]=None

    def create_values(self):
        return (
            self.set_id,
            self.set_name,
            self.set_code,
            self.set_type,
            self.released_at,
            self.digital,
            self.nonfoil_only,
            self.foil_only,
            self.parent_set
        )   
 
class UpdatedSet(BaseModel):
    set_name : str=Field(max_length=100, default=None)
    set_code : str=Field(max_length=10, default = None)
    set_type : str=Field(default=None)
    released_at : datetime.date=Field(default=None)
    digital : bool=Field(default=False)
    foil_status_id : str=(Field(max_length=20))
    parent_set : Optional[str]=None
    def create_values(self):
        return (
            self.set_name,
            self.set_code,
            self.set_type,
            self.released_at,
            self.digital,
            self.foil_status_id,
            self.parent_set
        )
 
class NewSets(BaseModel):
    items : List[NewSet]
 
    def __iter__(self):
        return iter(self.items)
    def __len__(self):
        return len(self.items)
    def __getitem__(self, index):
        return self.items[index]
