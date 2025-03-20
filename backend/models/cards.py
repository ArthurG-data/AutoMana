from pydantic import BaseModel, Field

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