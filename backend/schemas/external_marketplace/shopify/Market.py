from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class Market(BaseModel):
    name: str
    country_code: str
    city: str
    api_url: str

    class Config:
        orm_mode = True

class MarketInDb(Market):
    market_id: int
    created_at: datetime
    updated_at: datetime

class InsertMarket(Market):
    pass

class UpdateMarket(BaseModel):
    market_id: int
    name: Optional[str]=None
    country_code: Optional[str]=None
    city: Optional[str]=None
    api_url: Optional[str]=None

    class Config:
        orm_mode = True
    
