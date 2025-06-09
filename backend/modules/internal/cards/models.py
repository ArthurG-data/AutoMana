from pydantic import Field, model_validator, BaseModel, computed_field
from uuid import UUID
from typing import Optional,  List, Union
from backend.modules.public.cards.models import BaseCard

def process_type_line(card_type_line : str):
    super_types = {'Basic', 'Elite','Host', 'Legendary', 'Ongoing', 'Snow', 'World'}
    obsolet_map = {'Continuous Artifact' : 'Artifact','Interrupt' : 'Instant','Local enchantment' : 'Enchantment','Mana source':'Instant', 'Mono Artifact' : 'Artifact', 'Poly Artifact' : 'Artifact', 'Summon' : 'Creature'}
    CARD_TYPES = {
    "Artifact", "Creature", "Enchantment", "Instant", "Land", "Planeswalker",
    "Sorcery", "Kindred", "Dungeon", "Battle", "Plane", "Phenomenon", 
    "Vanguard", "Scheme", "Conspiracy"
    }
    supertypes = []
    types = []
    subtypes = []
    # check for double faced cards

    if "—" in card_type_line:
        main_part, sub_part = map(str.strip, card_type_line.split("—", 1))
        subtypes = sub_part.split()
    else:
        main_part = card_type_line

    for part in main_part.split():
        if part in super_types:
            supertypes.append(part)
        elif part in CARD_TYPES:
            types.append(part)
        elif part in obsolet_map:
            # Convert legacy types (e.g., Summon → Creature)
            types.append(obsolet_map[part])
        else:
            # If no clear mapping, assume it's an old or custom subtype
            subtypes.append(card_type_line)

    return {
        "supertypes": supertypes,
        "types": types,
        "subtypes": subtypes
    }


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
    