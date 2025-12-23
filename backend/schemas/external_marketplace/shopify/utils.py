from enum import Enum
from pydantic import BaseModel
from typing import Optional

import hashlib


def get_hashed_product_shop_id(product_id: str, shop_id: str) -> str:
    unique_str = f"{product_id}__{shop_id}"
    return hashlib.sha256(unique_str.encode()).hexdigest()


def extract_card_tag(body_html):
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(body_html, 'html.parser')
    meta = soup.find('div', class_='catalogMetaData')

    if meta and meta.has_attr('data-tcgid') and meta['data-tcgid'] != "":
        return int(meta['data-tcgid'])
    return None

class Status(str, Enum):
    DOWNLOADED = "downloaded"
    STAGED = "staged"
    VALIDATED = "validated"
    LOADED = "loaded"
    ARCHIVED = "archived"
    SKIPPED = "skipped"
    FAILED = "failed"
    RETRYING = "retrying"
    
class LogStatus(BaseModel):
    timestamp : str
    shop : str
    collection : Optional[str]=None
    page : int
    filename : str
    status :  Status

class AvailableShops(str, Enum):
    gg_brisbane = "Good Game - Brisbane"

