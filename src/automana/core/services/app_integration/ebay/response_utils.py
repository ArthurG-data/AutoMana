import logging

from automana.core.models.ebay import listings
import xml.etree.ElementTree as ET
from typing import List
import xmltodict

logger = logging.getLogger(__name__)

def clean_ebay_data(data):
    def strip_keys(obj):
        if isinstance(obj, dict):
            new_obj = {}
            for k, v in obj.items():
                key = k.lstrip('@#')
                new_obj[key] = strip_keys(v)
            return new_obj
        elif isinstance(obj, list):
            return [strip_keys(item) for item in obj]
        elif isinstance(obj, str):
            val = obj.lower()
            if val == "true":
                return True
            if val == "false":
                return False
            try:
                return float(obj) if '.' in obj else obj
            except ValueError:
                return obj
        return obj

    return strip_keys(data)

async def parse_listings_response(xml_text : str):
    ns = {'e': 'urn:ebay:apis:eBLBaseComponents'}
    root = ET.fromstring(xml_text)

    # Parse entire XML with xmltodict
    xml_dict = xmltodict.parse(xml_text)
    items_data = xml_dict.get("GetMyeBaySellingResponse", {}).get("ActiveList", {}).get("ItemArray", {}).get("Item")
    return await parse_multiple_items(items_data)


async def parse_single_item(xml_text: str) -> listings.ItemModel:
    xml_dict = xmltodict.parse(xml_text)
    item_data = xml_dict.get("GetItemResponse", {}).get("Item")
    flattened = clean_ebay_data(item_data)
    return listings.ItemModel(**flattened)
 
async def parse_multiple_items(items_data) -> List[listings.ItemModel]:
    if items_data is None:
        return []
    # Normalize single item to list
    if isinstance(items_data, dict):
        items_data = [items_data]
    results = []
    for raw_item in items_data:
        try:
            flattened = clean_ebay_data(raw_item )
            results.append(listings.ItemModel(**flattened))
        except Exception as e:
            logger.error("item_parse_error", extra={"error": str(e)})

    return results

def parse_verify_add_item_response(xml_text: str) -> dict:
    ns = {'e': 'urn:ebay:apis:eBLBaseComponents'}
    root = ET.fromstring(xml_text)
    
    ack = root.find("e:Ack", ns)
    item_id = root.find("e:ItemID", ns)
    errors = root.findall("e:Errors/e:LongMessage", ns)

    return {
        "ack": ack.text if ack is not None else "Unknown",
        "item_id": item_id.text if item_id is not None else None,
        "errors": [e.text for e in errors]
    }
