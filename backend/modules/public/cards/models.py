
from fastapi import Query
from pydantic import BaseModel, Field, model_validator
from uuid import UUID
from typing import Optional,  List, Union,Annotated

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

