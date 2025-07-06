import hashlib

def get_hashed_product_shop_id(product_id: str, shop_id: str) -> str:
    unique_str = f"{product_id}__{shop_id}"
    return hashlib.sha256(unique_str.encode()).hexdigest()