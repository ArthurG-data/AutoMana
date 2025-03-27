from pydantic import BaseModel, Field, field_validator
from enum import Enum
from typing import Optional
from datetime import date, datetime
from uuid import UUID, uuid4

### Collections schemas

class PublicCollection(BaseModel):
    username : str = Field(
        title='The ucollection owner',
    )
    
    collection_name : str=Field(
        title='The name of the collection'
    )
    
    is_active : bool=Field(
        default=True, title='Has the collection been deleted'
    )

class CreateCollection(BaseModel):
    collection_name : str=Field(
        title='The name of the collection',
        max_length=20
    )
    user_id : str=Field(
        title='The secret user id'
    )
class CollectionInDB(BaseModel):
    collection_id : str=Field(
        title='The unique secret collection id',
        default_factory=uuid4
    )
    collection_name : str=Field(
        title='The name of the collection'
    )
    user_id : str=Field(
        title='The secret user id'
    )
    created_at : datetime=Field(
        title='The date of the collection creation'
    )
    is_active : bool=Field(
        default=True, title='Has the collection been deleted'
    )

class UpdateCollection(BaseModel):
    collection_name : str | None=Field(
        default=None, 
        max_length=20
    )
    is_active : bool | None=None


### collection entries

class Conditions(Enum):
    D = 'D'
    G = 'G'
    NM = 'NM'
    Grd = 'Grd'



class CollectionEntry(BaseModel):
    collection_id : UUID
    entry_id : UUID = uuid4()
    card_version_id : UUID
    is_foil : bool=Field(
        default=False, title='Is the card foil'
    )
    purchase_date : date = Field(default_factory=date.today)
    purchase_price : float = Field(ge=0)
    condition : Conditions = Field(
        default='NM', title='The condition of the card, must be one of NM (near Mint), Grd (graded), G (good), D(Damaged)' 
    )
   

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

    

