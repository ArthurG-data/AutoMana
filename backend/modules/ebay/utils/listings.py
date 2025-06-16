from backend.modules.ebay.models import listings
import xml.etree.ElementTree as ET 
from typing import List, Any
from xml.dom.minidom import parseString
from pydantic import BaseModel
import xmltodict
from backend.modules.ebay.utils import listings as listing_utils

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
    flattened = listing_utils.clean_ebay_data(item_data)
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
            flattened = listing_utils.clean_ebay_data(raw_item )
            results.append(listings.ItemModel(**flattened))
        except Exception as e:
            print(f"Error parsing item: {e}")

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

def to_xml_element(parent: ET.Element, name: str, value: Any):
    if value is None:
        return
    if isinstance(value, BaseModel):
        child = ET.SubElement(parent, name)
        for sub_name, sub_value in value:
            to_xml_element(child, sub_name, sub_value)
    elif isinstance(value, list):
        for item in value:
            to_xml_element(parent, name, item)
    elif isinstance(value, dict):
        child = ET.SubElement(parent, name)
        for k, v in value.items():
            to_xml_element(child, k, v)
    else:
        ET.SubElement(parent, name).text = str(value)

def item_to_xml(item: listings.ItemModel) -> str:
    item_elem = ET.Element("Item")
    for field_name, value in item:
        to_xml_element(item_elem, field_name, value)
    return parseString(ET.tostring(item_elem)).toprettyxml(indent="  ")