from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum
from typing import Optional
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

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


class Finish(str, Enum):
    NONFOIL = 'NONFOIL'
    FOIL = 'FOIL'
    ETCHED = 'ETCHED'


class AddCollectionEntryRequest(BaseModel):
    """
    Identifies a card version by one of three strategies, then attaches entry metadata.
    Exactly one identifier group must be provided.
    """
    # --- identifier (one of the three must be set) ---
    card_version_id: Optional[UUID] = Field(default=None, description="Internal card_version_id (returned by /suggest)")
    scryfall_id: Optional[str] = Field(default=None, description="Scryfall UUID for the printing")
    set_code: Optional[str] = Field(default=None, max_length=10, description="Set code (e.g. 'dmu'), use with collector_number")
    collector_number: Optional[str] = Field(default=None, max_length=50, description="Collector number (e.g. '108'), use with set_code")

    # --- entry metadata ---
    condition: Conditions = Field(default=Conditions.NM)
    finish: Finish = Field(default=Finish.NONFOIL)
    purchase_price: Decimal = Field(ge=0, decimal_places=2)
    currency_code: str = Field(default='USD', max_length=3)
    purchase_date: date = Field(default_factory=date.today)
    language_id: Optional[int] = Field(default=None)

    @model_validator(mode='after')
    def check_identifier(self) -> 'AddCollectionEntryRequest':
        has_internal = self.card_version_id is not None
        has_scryfall = self.scryfall_id is not None
        has_tuple = self.set_code is not None and self.collector_number is not None
        if not (has_internal or has_scryfall or has_tuple):
            raise ValueError(
                "Provide one of: card_version_id, scryfall_id, or set_code+collector_number"
            )
        return self


class PublicCollectionEntry(BaseModel):
    item_id: UUID
    card_version_id: UUID
    card_name: str
    set_code: str
    collector_number: str
    finish: Finish
    purchase_date: date
    purchase_price: Decimal
    condition: Conditions
    currency_code: str
    language_id: Optional[int] = None


class UpdateCollectionEntry(BaseModel):
    finish: Optional[Finish] = None
    purchase_date: Optional[date] = None
    purchase_price: Optional[Decimal] = None
    condition: Optional[Conditions] = None
    currency_code: Optional[str] = Field(default=None, max_length=3)
    language_id: Optional[int] = None


class CollectionEntryInDB(BaseModel):
    item_id: UUID
    collection_id: UUID
    card_version_id: UUID
    finish_id: int
    purchase_date: date
    purchase_price: Decimal
    condition: str
    currency_code: str
    language_id: Optional[int] = None
   