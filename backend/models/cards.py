from pydantic import BaseModel, Field, field_validator, model_validator
import datetime
from uuid import UUID
from typing import Optional, Sequence, List, Union

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


   