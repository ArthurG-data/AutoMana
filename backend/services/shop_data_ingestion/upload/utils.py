import hashlib
from bs4 import BeautifulSoup

def get_hashed_product_shop_id(product_id: str, shop_id: str) -> str:
    unique_str = f"{product_id}__{shop_id}"
    return hashlib.sha256(unique_str.encode()).hexdigest()

def extract_card_tag(body_html):
    soup =BeautifulSoup(body_html, 'html.parser')
    meta = soup.find('div', class_='catalogMetaData')
  
    if meta and meta.has_attr('data-tcgid') and meta['data-tcgid'] != "":
        return int(meta['data-tcgid'])
    return None