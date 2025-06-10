from pydantic import BaseModel, Field, field_validator, computed_field
import datetime
from uuid import UUID
from typing import Optional, List



class NewSet(BaseModel):
    id : UUID
    name : str=Field(max_length=100)
    code : str=Field(max_length=10)
    set_type : str=Field(max_length=30)
    released_at : datetime.date
    digital : bool=Field(default=False)
    nonfoil_only : bool=Field(default=False)
    foil_only : bool=Field(default=False)
    parent_set_code : Optional[str]=None
    icon_svg_uri : str 
        
    @field_validator("icon_svg_uri", mode="before")
    @classmethod
    def extract_icon_query(cls, value:str)-> str:
 
       parsed_url = value.split('?')[-1]
       return parsed_url 

 
class NewSets(BaseModel):
    items : List[NewSet]
 
    @computed_field
    @property
    def count(self) -> int:
        return len(self.items)
    
class UpdatedSet(BaseModel):
    set_name : str=Field(max_length=100, default=None)
    set_code : str=Field(max_length=10, default = None)
    set_type : str=Field(default=None)
    released_at : datetime.date=Field(default=None)
    digital : bool=Field(default=False)
    foil_status_id : str=(Field(max_length=20))
    parent_set : Optional[str]=None
