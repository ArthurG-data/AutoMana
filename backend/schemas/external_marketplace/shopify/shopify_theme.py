from backend.schemas.external_marketplace.shopify.utils import get_hashed_product_shop_id, extract_card_tag
from pydantic import BaseModel, model_validator
from typing import Any, List, Optional, Tuple
from datetime import datetime
from decimal import Decimal,  getcontext

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
    
class InsertTheme(BaseModel):
    code : str
    name : str

class UpdateTheme(BaseModel):
    theme_id : int
    code : Optional[str] = None
    name : Optional[str] = None

class InsertCollection(BaseModel):
    market_id : int
    name : str

class UpdateCollection(BaseModel):
    handle_id : str
    market_id : str
    name : Optional[str]= None

class InsertCollectionTheme(BaseModel):
    theme_code : str
    collection_name : str

class CollectionModelInDB(BaseModel):
    id: int
    name: str
    market_id: int
    created_at: datetime
    updated_at: datetime

class ProductPrice(BaseModel):
    shop_id : int
    product_id : int
    tcgplayer_id : Optional[int] = None  # TCGPlayer product ID, if applicable
    product_shop_id : Optional[str] = None  # Unique identifier for the product in the shop
    price : Decimal
    foil_price : Optional[Decimal]= None
    currency : str = 'AUD'
    price_usd : Optional[Decimal] = None  
    foil_price_usd : Optional[Decimal] = None
    source : Optional[str]=None
    html_body : Optional[str] = None  # HTML body of the product page, if available
    created_at : datetime
    updated_at : datetime


    def batch_tuple_card(
        self
    ) -> Tuple[int, str, datetime, datetime]:
        return (
            self.tcgplayer_id,
            self.product_shop_id,
            self.created_at,
            self.updated_at
        )
    def batch_tuple(
        self,
        price_field: str,
        usd_field: str,
        is_foil_flag: bool = False,
        default_source: str = "scrapping_service"
    ) -> Tuple[datetime, str, Decimal, str, Decimal, bool, str]:
        base_price = getattr(self, price_field)
        usd_price  = getattr(self, usd_field) or base_price
        source     = self.source or default_source
        return (
            self.updated_at,
            self.product_shop_id,
            base_price,
            self.currency,
            usd_price,
            is_foil_flag,
            source,
        )
    
    @model_validator(mode='after')
    def create_product_shop_id(self):
        if not self.product_shop_id:
            self.product_shop_id = get_hashed_product_shop_id(self.product_id, self.shop_id)
        if self.html_body:
            self.tcgplayer_id = extract_card_tag(self.html_body)
        return self

class BatchProductProces(BaseModel):
    items : List[ProductPrice]

    def __iter__(self):
        return iter(self.items)
    
    def __len__(self):
        # allow: len(batch_proc)
        return len(self.items)
    def __getitem__(self, index):
        # allow: batch_proc[0], slicing, etc.
        return self.items[index]

    def prepare_prodcut_card_batches (
        self
    )-> Tuple[List[int], List[str], List[datetime], List[datetime]]:
        batch =[p.batch_tuple_card() for p in self.items if p.tcgplayer_id is not None]
        return tuple(map(list, zip(*batch )))
    
    def prepare_price_batches(
        self,
        include_foil: bool = False
    ) -> Tuple[
        Tuple[List[datetime], List[str], List[Decimal], List[str], List[Decimal], List[bool], List[str]],
        Optional[Tuple[List[datetime], List[str], List[Decimal], List[str], List[Decimal], List[bool],List[str]]]
    ]:
        """
        Returns a tuple: (normal_batch, foil_batch or None).
        Each batch is a 7-tuple of parallel lists.
        """
        # Build normal batch
        normal = [p.batch_tuple('price', 'price_usd') for p in self.items]
        normal_batch = tuple(map(list, zip(*normal)))

        if not include_foil:
            return normal_batch, None

        # Build foil batch
        foil = [p.batch_tuple('foil_price', 'foil_price_usd',  is_foil_flag=True) for p in self.items if p.foil_price is not None]
        if not foil:
            return normal_batch, None
        foil_batch = tuple(map(list, zip(*foil)))
        return normal_batch, foil_batch
