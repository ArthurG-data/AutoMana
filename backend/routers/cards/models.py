
from fastapi import Query
from pydantic import BaseModel, Field, model_validator
from uuid import UUID
from typing import Optional,  List, Union,Annotated
from backend.routers.cards.utils import process_type_line

class CommonQueryParams:
    def __init__ (self, q : str | None=None, skip: Annotated[int, Query(ge=0)] =0, limit: Annotated[int , Query(ge=1, le=50)]= 10):
        self.q = q,
        self.skip = skip,
        self.limit = limit

class BaseCard(BaseModel):
    card_name: str = Field(alias="name", title="The name of the card")
    set_name: str = Field(alias="set_name", title="The complete name of the set")
    set_code: str = Field(alias="set", title="The abbreviation of the set")
    cmc: int
    rarity_name: str = Field(alias="rarity", title="The rarity of the card")
    oracle_text: Optional[str] = Field(default="", title="The text on the card")
    digital: bool = Field(alias="digital", title="Is the card released only on digital platform")

class CreateCard(BaseCard):
    artist: str = Field(max_length=100)
    illustration_id: Optional[UUID] = None
    mana_cost : str=Field(max_length=100)
    collector_number: Union[int, str] = Field(max_length=50)
    border_color: str = Field(max_length=20)
    frame: str = Field(max_length=20)
    layout: str = Field(max_length=20)
    is_promo: bool = Field(alias="promo")
    is_digital: bool = Field(alias="digital")
    keywords: List[str]
    type_line: str
    color_produced: Optional[List[str]] = Field(alias="produced_mana", default=None)
    card_color_identity: List[str] = Field(alias="color_identity")
    legalities : dict
    supertypes: List[str] = []
    types: List[str] = []
    subtypes: List[str] = []
    reserved : bool=Field(default=False)
   
    @model_validator(mode='after')
    def process_type_line(cls, values):
    
        parsed = process_type_line(values.type_line)
        values.types = parsed["types"]
        values.supertypes = parsed["supertypes"]
        values.subtypes = parsed["subtypes"]
        return values

