from pydantic import BaseModel, Field, field_validator
from enum import Enum
from typing import Optional
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

### Collections schemas

class PublicCollection(BaseModel):
    collection_id: UUID = Field(title='The unique collection ID')
    username: str = Field(title='The collection owner')
    description: str = Field(title='The description of the collection')
    collection_name: str = Field(title='The name of the collection')
    created_at: datetime = Field(title='The date the collection was created')
    is_active: bool = Field(default=True, title='Has the collection been deleted')

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
    collection_id: UUID = Field(title='The unique secret collection id')
    collection_name: str = Field(title='The name of the collection')
    description: str = Field(title='The description of the collection')
    user_id: UUID = Field(title='The secret user id')
    created_at: datetime = Field(title='The date of the collection creation')
    is_active: bool = Field(default=True, title='Has the collection been deleted')

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

class Conditions(str, Enum):
    NM = 'NM'
    LP = 'LP'
    MP = 'MP'
    HP = 'HP'
    DMG = 'DMG'
    SP = 'SP'

class PublicCollectionEntry(BaseModel):
    unique_card_id: UUID = Field(title='The card version ID')
    is_foil: bool = Field(default=False, title='Is the card foil')
    purchase_date: date = Field(default_factory=date.today)
    purchase_price: Decimal = Field(ge=0, decimal_places=2)
    condition: Conditions = Field(default=Conditions.NM, title='Card condition')
    currency_code: str = Field(default='USD', max_length=3, title='Purchase currency')
    language_id: Optional[int] = Field(default=None, title='Card language (language_id from card_catalog.language_ref)')

class NewCollectionEntry(PublicCollectionEntry):
    collection_id: UUID = Field(title='The collection ID')

class CollectionEntryInDB(NewCollectionEntry):
    item_id: UUID

class UpdateCollectionEntry(BaseModel):
    is_foil: Optional[bool] = None
    purchase_date: Optional[date] = None
    purchase_price: Optional[Decimal] = None
    condition: Optional[Conditions] = None
    currency_code: Optional[str] = Field(default=None, max_length=3)
    language_id: Optional[int] = None
   