from typing import Annotated, Any, Callable, Dict
import xmltodict
import xml.etree.ElementTree as ET 
from backend.schemas.app_integration.ebay.listings import  BaseModel,ItemModel

def to_xml_element(parent: ET.Element, name: str, value: Any):
        if value is None:
            return
        if isinstance(value, BaseModel):
            child = ET.SubElement(parent, name)
            for sub_name, sub_value in value.model_dump(exclude_none=True).items():
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

REQUEST_GENERATORS: Dict[str, Callable[..., str]] = {}

def register_request_generator(request_type: str):
    """
    Decorator to register a request generator function in the factory.

    Args:
        request_type: The type of eBay API request (e.g., "AddFixedPriceItemRequest").
    """
    def decorator(func: Callable[..., str]):
        REQUEST_GENERATORS[request_type] = func
        return func
    return decorator

def generate_ebay_request_xml(request_type: str, **kwargs) -> str:
    """
    Generate XML for various eBay Trading API requests using the factory.

    Args:
        request_type: The type of eBay API request (e.g., "AddFixedPriceItemRequest").
        kwargs: Additional parameters for the request generator.

    Returns:
        A string containing the XML request body.
    """
    generator = REQUEST_GENERATORS.get(request_type)
    if not generator:
        raise ValueError(f"Unsupported request type: {request_type}")
    return generator(**kwargs)

@register_request_generator("AddFixedPriceItemRequest")
def generate_add_fixed_price_item_request_xml(item: ItemModel) -> str:
    root = ET.Element("AddFixedPriceItemRequest", xmlns="urn:ebay:apis:eBLBaseComponents")
    ET.SubElement(root, "ErrorLanguage").text = "en_US"
    ET.SubElement(root, "WarningLevel").text = "High"

    item_element = ET.SubElement(root, "Item")
    for field_name, field_value in item.model_dump(exclude_none=True).items():
        to_xml_element(item_element, field_name, field_value)

    return ET.tostring(root, encoding="utf-8", method="xml").decode("utf-8")

@register_request_generator("ReviseItemRequest")
def generate_revise_item_request_xml(item: ItemModel) -> str:
    if not item.ItemID:
        raise ValueError("ItemID is required to revise a listing.")

    root = ET.Element("ReviseItemRequest", xmlns="urn:ebay:apis:eBLBaseComponents")
    ET.SubElement(root, "ErrorLanguage").text = "en_US"
    ET.SubElement(root, "WarningLevel").text = "High"

    item_element = ET.SubElement(root, "Item")
    for field_name, field_value in item.model_dump(exclude_none=True).items():
        to_xml_element(item_element, field_name, field_value)

    return ET.tostring(root, encoding="utf-8", method="xml").decode("utf-8")

@register_request_generator("EndItemRequest")
def generate_end_item_request_xml(item_id: str, reason: str = "NotAvailable") -> str:
    root = ET.Element("EndItemRequest", xmlns="urn:ebay:apis:eBLBaseComponents")
    ET.SubElement(root, "ErrorLanguage").text = "en_US"
    ET.SubElement(root, "WarningLevel").text = "High"
    ET.SubElement(root, "ItemID").text = item_id
    ET.SubElement(root, "EndingReason").text = reason

    return ET.tostring(root, encoding="utf-8", method="xml").decode("utf-8")

@register_request_generator("GetItemRequest")
def generate_get_item_request_xml(item_id: str) -> str:
    root = ET.Element("GetItemRequest", xmlns="urn:ebay:apis:eBLBaseComponents")
    ET.SubElement(root, "ErrorLanguage").text = "en_US"
    ET.SubElement(root, "WarningLevel").text = "High"
    ET.SubElement(root, "ItemID").text = item_id

    return ET.tostring(root, encoding="utf-8", method="xml").decode("utf-8")

@register_request_generator("GetMyeBaySellingRequest")
def generate_get_my_ebay_selling_request_xml(entries_per_page: int = 3, page_number: int = 1) -> str:
    root = ET.Element("GetMyeBaySellingRequest", xmlns="urn:ebay:apis:eBLBaseComponents")
    ET.SubElement(root, "ErrorLanguage").text = "en_US"
    ET.SubElement(root, "WarningLevel").text = "High"
    active_list = ET.SubElement(root, "ActiveList")
    ET.SubElement(active_list, "Sort").text = "TimeLeft"

    # Add Pagination block
    pagination = ET.SubElement(active_list, "Pagination")
    ET.SubElement(pagination, "EntriesPerPage").text = str(entries_per_page)
    ET.SubElement(pagination, "PageNumber").text = str(max(page_number, 1))

    return '<?xml version="1.0" encoding="utf-8"?>' + ET.tostring(root, encoding="utf-8", method="xml").decode("utf-8")
