import json
from pydantic import BaseModel, Field
import datetime
from uuid import UUID
from typing import Dict, Optional, List, Any

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
    set_id : UUID=Field(alias='id')
    set_name : str=Field(alias='name', max_length=100)
    set_code : str=Field(alias='code', max_length=10)
    set_type : str=Field(alias='type', max_length=30)
    released_at : datetime.date=Field(alias='released_at')
    digital : bool=Field(alias='digital', default=False)
    nonfoil_only : bool=Field(alias='nonfoil_only', default=False)
    foil_only : bool=Field(alias='foil_only', default=False)
    parent_set : Optional[str]=Field(alias='parent_set', default=None)
    #icon_svg_uri : Optional[str]=Field(alias='icon_svg_uri', default=None)

    class Config:
        populate_by_name = True  # Important for handling aliases
        from_attributes = True

    def model_dump_for_sql(self) -> Dict[str, Any]:
        """
        Use Pydantic's built-in serialization with custom transformations
        """
        # Get the standard model dump
        data = self.model_dump(
            by_alias=True,  # Use field aliases
            exclude_none=False,  # Keep None values for proper handling
            mode='json'  # JSON-serializable format
        )
        return {
            'id': data['id'],
            'name': data['name'],
            'code': data['code'],
            'set_type': data['type'],
            'released_at': data['released_at'],
            'digital': data['digital'],
            'nonfoil_only': data['nonfoil_only'],
            'foil_only': data['foil_only'],
            'parent_set_code': data['parent_set'],
        }

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
    def __setitem__(self, index, value):
        self.items[index] = value
    def __delitem__(self, index):
        del self.items[index]
    
    def model_dump_for_db(self) -> List[Dict[str, Any]]:
        """
        Alternative: Use model_dump with custom serialization
        """
        return [item.model_dump_for_sql() for item in self.items]

    def prepare_for_db(self) -> str:
        set_data = self.model_dump_for_db()
        return json.dumps(set_data)
