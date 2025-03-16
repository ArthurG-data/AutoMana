from pydantic import BaseModel, Field, EmailStr
from datetime import datetime
from enum import Enum


class BaseCard(BaseModel):
    card_version_id : str
    unique_card_id : str
    oracle_text : str | None = None
    set_id : str
    collector_number : str
    rarity_id : int = Field(ge=0, le=5)
    frame_id : int = Field(ge=0)
    layout_id : int = Field(ge=0)
    is_promo : bool
    is_digital : bool

class Cookies(BaseModel):
    session_id : str
    auth : bool
    user : str


class ObjectName(str, Enum):
    cards = 'cards'
    sets = 'sets'
