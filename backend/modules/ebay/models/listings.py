from pydantic import BaseModel, HttpUrl, model_validator
from typing import Optional, List

class ActiveListing(BaseModel):
    item_id: str
    title: str
    buy_it_now_price: float
    currency: str
    start_time: str
    time_left: str
    quantity: int
    quantity_available: int
    current_price: float
    view_url: HttpUrl
    image_url: Optional[HttpUrl]
    
class ActiveListingResponse(BaseModel):
    item_number : Optional[int]
    items : List[ActiveListing]
    @model_validator(mode='after')
    def set_item_number(self) -> "ActiveListingResponse":
        self.item_number = len(self.items)
        return self


