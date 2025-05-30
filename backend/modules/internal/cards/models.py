from pydantic import Field, model_validator
from uuid import UUID
from typing import Optional,  List, Union,Annotated
from backend.modules.cards.utils import process_type_line
from backend.models


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

