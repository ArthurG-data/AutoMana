import hashlib
import json
from backend.services.redis_cache import set_to_cache, get_from_cache

def _hash_query_params(params: dict) -> str:
    """Create a short hash from the query parameters."""
    query_string = json.dumps(params, sort_keys=True)
    return hashlib.md5(query_string.encode()).hexdigest()

def cache_ebay_search(params: dict, response: dict, ttl: int = 1800):
    key = f"ebay:search:{_hash_query_params(params)}"
    set_to_cache(key, response, expiry_seconds=ttl)

def get_cached_ebay_search(params: dict) -> dict | None:
    key = f"ebay:search:{_hash_query_params(params)}"
    return get_from_cache(key)

def cache_ebay_item(item_id: str, response: dict, ttl: int = 86400):
    key = f"ebay:item:{item_id}"
    set_to_cache(key, response, expiry_seconds=ttl)

def get_cached_ebay_item(item_id: str) -> dict | None:
    key = f"ebay:item:{item_id}"
    return get_from_cache(key)