
from pydantic import BaseModel, model_validator
from typing import Any, List, Optional
from datetime import datetime


class ShopifyBaseModel(BaseModel):
    id: int
    title: str
    handle: str
    published_at: datetime
    updated_at: datetime

class ImageField(BaseModel):
    id : int
    src : str
    alt : Optional[Any]=None
    width : Optional[int]=None
    height : Optional[int]=None


class Variant(BaseModel):
    id : int
    title : str
    sku : str
    requires_shipping : bool
    taxable : bool
    available :bool
    price : float
    product_id : int
    created_at : str
    updated_at : str
    
class OptionModel(BaseModel):
    name : str
    values : List[str]
         
class CollectionModel(ShopifyBaseModel):
    description : Optional[str]=None
    image : Optional[ImageField]=None
    products_count : int
        
class ProductModel(ShopifyBaseModel):
    body_html: Optional[str] = None
    created_at: str
    vendor: str
    product_type: str
    tags: List[str]
    variants: List[Variant]
    images: List[ImageField]
    options: List[OptionModel]

#T = TypeVar("T", bound=ShopifyBaseModel)

class ResponseModel(BaseModel):
    items : List[ShopifyBaseModel]
    count : Optional[int]=0
    
    @model_validator(mode='after')
    def count_items(self):
        self.count = len(self.items)
        return self