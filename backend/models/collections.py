from pydantic import BaseModel, Field
from typing import Optional
import datetime

class BaseCollection(BaseModel):
    user_id : str = Field(
        title='The unique secret collection owner'
    )
    collection_id : str =Field(
        title='The collection id'
    )
    collection_name : str=Field(
        title='The name of the collection'
    )
    created_at : datetime=Field(
        title='The date of the collection creation'
    )
    is_active : bool=Field(
        title='Has the collection been deleted'
    )


class CollectionEntry(BaseModel):
    collection_id : str
    entry_id : str
    card_version_id : str
    is_foil : bool
    purchase_data : datetime
    purchase_price : float
    condition : int
    profit: Optional[float] = None

class order_items(BaseModel):
    order_id : str
    entry_id : str
    order_item_status_code : str
    order_item_quantity : int
    order_item_price : float
    fee : float
    platform : int

class shipment(BaseModel):
    shipment_id : int
    order_id : int
    invoice_number : int
    shipment_tracking_number : int
    shipment_date : datetime
    other_details : str | None=None

class invoice(BaseModel):
    invoice_id : int
    order_id : int
    invoice_data : datetime
    invoice_status_code : int


class orders(BaseModel):
    customer_id : str
    order_id : str
    order_status : int
    date_order : int
    order_details : str
    
class customer(BaseModel):
    custome_id : str
    customer_type : str
    first_name : str
    middle_initial : str
    last_name : str
    gender : int
    customer_username : str
    customer_email : str
    phone_number : str
    address_line_1 : str
    address_line_2 : str
    address_line_3 : str
    address_line_4 : str
    country :str
    city : str
    province : str

    

