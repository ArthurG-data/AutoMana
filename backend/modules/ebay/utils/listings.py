from backend.modules.ebay.models import listings
import xml.etree.ElementTree as ET 
from typing import List, Any
from xml.dom.minidom import parseString
from pydantic import BaseModel



def extract_total_pages(xml_text: str):
    ns = {'e': 'urn:ebay:apis:eBLBaseComponents'}
    root = ET.fromstring(xml_text)
    page_number = root.findall(".//e:TotalNumberOfPages", ns)
    return page_number

def parse_single_item(item: ET.Element, ns: dict) -> listings.ActiveListing:
    return listings.ActiveListing(
        item_id=item.find("e:ItemID", ns).text,
        title=item.find("e:Title", ns).text,
        buy_it_now_price=float(item.find("e:BuyItNowPrice", ns).text),
        currency=item.find("e:BuyItNowPrice", ns).attrib.get("currencyID"),
        start_time=item.find("e:ListingDetails/e:StartTime", ns).text,
        time_left=item.find("e:TimeLeft", ns).text,
        quantity=int(item.find("e:Quantity", ns).text),
        quantity_available=int(item.find("e:QuantityAvailable", ns).text),
        current_price=float(item.find("e:SellingStatus/e:CurrentPrice", ns).text),
        view_url=item.find("e:ListingDetails/e:ViewItemURL", ns).text,
        image_url=(item.find("e:PictureDetails/e:GalleryURL", ns).text
                   if item.find("e:PictureDetails/e:GalleryURL", ns) is not None else None)
    )


def parse_active_listings(xml_text: str) -> listings.ActiveListingResponse:
    ns = {'e': 'urn:ebay:apis:eBLBaseComponents'}
    root = ET.fromstring(xml_text)
    items = root.findall(".//e:Item", ns)
    parsed_items: List[listings.ActiveListing] = []
    
    for item in items:
        try:
            parsed = parse_single_item(item, ns)
            parsed_items.append(parsed)
        except Exception as e:
            print(f"Error parsing item: {e}")
    return parsed_items

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