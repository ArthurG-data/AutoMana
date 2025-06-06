from pydantic import Field, model_validator, BaseModel
from uuid import UUID
from typing import Optional,  List, Union,Annotated, Any
from backend.modules.internal.cards.utils import process_type_line, to_json_safe
from backend.modules.public.cards.models import BaseCard


class CardFace(BaseModel):
    name: str
    face_index : Optional[int] = 0
    mana_cost: Optional[str] = None
    type_line: str
    oracle_text: Optional[str] = None
    power: Optional[Union[int, str]] = None
    toughness: Optional[Union[int, str]] = None
    flavor_text: Optional[str] = None
    artist: Optional[str] = None
    artist_id: Optional[UUID] = None
    illustration_id: Optional[UUID] = None
    supertypes: List[str] = []
    types: List[str] = []
    subtypes: List[str] = []

    @model_validator(mode='after')
    def process_type_line(cls, values):
    
        parsed = process_type_line(values.type_line)
        values.types = parsed["types"]
        values.supertypes = parsed["supertypes"]
        values.subtypes = parsed["subtypes"]
        return values



def parse_card_faces(raw_faces_list: list[dict]) -> list[CardFace]:
    
    card_faces = []
    for i in range(len(raw_faces_list)):
        face_data = raw_faces_list[i]
        face_data["face_index"] = i
        card_face = CardFace(**face_data)

        card_faces.append(card_face)
    return card_faces


class CreateCard(BaseCard):
    artist: str = Field(max_length=100)
    artist_ids : List[UUID] = []
    illustration_id: Optional[UUID] = None
    games : List[str] = []
    mana_cost : Optional[str]=Field(max_length=100, default=None)
    collector_number: Union[int, str] 
    border_color: str = Field(max_length=20)
    frame: str = Field(max_length=20)
    layout: str = Field(max_length=20)
    is_promo: bool = Field(alias="promo")
    is_digital: bool = Field(alias="digital")
    keywords: Optional[List[str]]=[]
    type_line: Optional[str]=None
    oversized : Optional[bool]=False
    color_produced: Optional[List[str]] = Field(alias="produced_mana", default=None)
    card_color_identity: List[str] = Field(alias="color_identity")
    legalities : dict
    supertypes: List[str] = []
    types: List[str] = []
    subtypes: List[str] = []
    promo : Optional[bool]=False
    booster : Optional[bool]=True
    full_art : Optional[bool]=False
    flavor_text : Optional[str] = None
    textless : Optional[bool]=False
    power : Optional[int|str] = None
    lang : Optional[str]='en'
    promo_types : Optional[List[str]]=[]
    toughness : Optional[int|str]=[]
    variation : Optional[bool]=False
    reserved : bool=Field(default=False)
    card_faces : Optional[List[CardFace]]=None

    @model_validator(mode='before' )
    #in prograss
    def parse_card_faces(cls, values):
        faces = values.get('card_faces')
        if faces:
            values["card_faces"] = parse_card_faces(faces)
        return values
   
    @model_validator(mode='after')
    def process_type_line(cls, values):
    
        parsed = process_type_line(values.type_line)
        values.types = parsed["types"]
        values.supertypes = parsed["supertypes"]
        values.subtypes = parsed["subtypes"]
        return values

