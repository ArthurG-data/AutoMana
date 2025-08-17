from pydantic import BaseModel, Field, field_validator
from enum import Enum
from typing import Optional
from datetime import date, datetime
from uuid import UUID, uuid4

### Collections schemas

class PublicCollection(BaseModel):
    username : str = Field(
        title='The collection owner',
    )
    description : str=Field(
        title='The description of the collection'
    )
    collection_name : str=Field(
        title='The name of the collection'
    )
    
    is_active : bool=Field(
        default=True, title='Has the collection been deleted'
    )

class CreateCollection(BaseModel):
    collection_name : str=Field(
        title='The name of the collection',
        max_length=20
    )
    description : str=Field(
        title='The description of the collection',
        max_length=100
    )

class CollectionInDB(BaseModel):
    collection_id : UUID=Field(
        title='The unique secret collection id'
    )
    collection_name : str=Field(
        title='The name of the collection'
    )
    description : str=Field(
        title='The description of the collection'
    )
    user_id : str=Field(
        title='The secret user id'
    )
    created_at : datetime=Field(
        title='The date of the collection creation'
    )
    is_active : bool=Field(
        default=True, title='Has the collection been deleted'
    )

class UpdateCollection(BaseModel):
    collection_name : str | None=Field(
        default=None, 
        max_length=20
    )
    description : str | None=Field(
        default=None, 
        max_length=100
    )
    is_active : bool | None=None

class Conditions(Enum):
    D = 'D'
    G = 'G'
    NM = 'NM'
    Grd = 'Grd'

class PublicCollectionEntry(BaseModel):
    unique_card_id : UUID=Field(title='The card ID')
    is_foil : bool=Field(
        default=False, title='Is the card foil'
    )
    purchase_date : date = Field(default_factory=date.today)
    purchase_price : float = Field(ge=0)
    condition : Conditions = Field(
        default='NM', title='The condition of the card, must be one of NM (near Mint), Grd (graded), G (good), D(Damaged)' 
    )

class NewCollectionEntry(PublicCollectionEntry):
    collection_id : UUID=Field(title='The collection ID')
   
class CollectionEntryInDB(NewCollectionEntry):
    item_id : UUID

class UpdateCollectionEntry(BaseModel):
    is_foil : Optional[bool] =None
    purchase_date : Optional[date] = None
    purchase_price : Optional[float] = None
    condition : Optional[Conditions] = None
   