from pydantic import Field, model_validator, BaseModel, computed_field
from uuid import UUID
from typing import Optional,  List, Union
from backend.utils_new.card_catalog.type_parser import process_type_line
from backend.utils_new.card_catalog.card_face_parser import parse_card_faces

class BaseCard(BaseModel):
    name: str = Field(alias="card_name", title="The name of the card")
    set_name: str = Field(title="The complete name of the set")
    set: str = Field(alias="set_code", title="The abbreviation of the set")
    cmc: int
    rarity: str = Field(alias="rarity_name", title="The rarity of the card")
    oracle_text: Optional[str] = Field(default="", title="The text on the card")
    digital: bool = Field(title="Is the card released only on digital platform")
    
    class Config:
        populate_by_name = True  # Important for handling aliases
        from_attributes = True


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

class CreateCard(BaseCard):
    artist: str = Field(max_length=100)
    artist_ids : List[UUID] = []
    cmc : int=Field(default=0)
    illustration_id: Optional[UUID] = '00000000-0000-0000-0000-000000000001'
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
    card_faces : List[CardFace]=[],
    set_name : str=Field('MISSING_SET')
    set : str
    set_id : UUID
    

    @model_validator(mode='before')
    @classmethod
    def parse_and_clean_card_faces(cls, values):
        faces = values.get("card_faces")

        if faces is None:
            values["card_faces"] = []
        else:
            # If faces is a dict → call your parse_card_faces() function
            if isinstance(faces, dict):
                faces = parse_card_faces(faces)  # returns List[CardFace]

            # Now clean the list
            clean_faces = []
            for face in faces:
                if face is None:
                    continue
                if isinstance(face, CardFace):
                    clean_faces.append(face)
                elif isinstance(face, dict):
                    clean_faces.append(CardFace(**face))
                else:
                    raise ValueError(f"Invalid card_face entry: {face}")

            values["card_faces"] = clean_faces

        return values
    
    @model_validator(mode='after')
    def process_type_line(cls, values):
    
        parsed = process_type_line(values.type_line)
        values.types = parsed["types"]
        values.supertypes = parsed["supertypes"]
        values.subtypes = parsed["subtypes"]
        return values
    

class CreateCards(BaseModel):
 
    items :List[CreateCard] = []

    def __iter__(self):
        return iter(self.items)

    @computed_field
    @property
    def count(self) -> int:
        return len(self.items)
    