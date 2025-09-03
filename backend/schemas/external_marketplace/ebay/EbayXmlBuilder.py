from pydantic import BaseModel, Field
from typing import Dict,  Optional, Any, List
import xml.etree.ElementTree as ET 
import xmltodict
from backend.schemas.app_integration.ebay.listings import  BaseModel,ItemModel

class EbayXmlBuilder:
    """Builder class for eBay Trading API XML requests"""
    
    NAMESPACE = "urn:ebay:apis:eBLBaseComponents"

    def __init__(self, request_name: str):
        """Initialize a new XML builder with the specified request name"""
        self.root = ET.Element(f"{request_name}", xmlns=self.NAMESPACE)
        self._add_standard_elements()

    def _add_standard_elements(self):
        """Add standard elements to all requests"""
        ET.SubElement(self.root, "ErrorLanguage").text = "en_US"
        ET.SubElement(self.root, "WarningLevel").text = "High"
    
    def add_element(self, name: str, value: Optional[Any] = None):
        """Add an element to the root with optional value"""
        if value is not None:
            element = ET.SubElement(self.root, name)
            element.text = str(value)
        return self
    
    def add_nested_element(self, parent_name: str, elements: Dict[str, Any]):
        """Add a nested element with child elements"""
        parent = ET.SubElement(self.root, parent_name)
        for name, value in elements.items():
            if value is not None:
                child = ET.SubElement(parent, name)
                child.text = str(value)
        return self
    
    def _dict_to_xml(self, parent: ET.Element, name: str, data: Dict[str, Any]):
        """Convert a dictionary to XML elements"""
        element = ET.SubElement(parent, name)
        for key, value in data.items():
            if value is None:
                continue
            elif isinstance(value, dict):
                self._dict_to_xml(element, key, value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._dict_to_xml(element, key, item)
                    else:
                        child = ET.SubElement(element, key)
                        child.text = str(item)
            else:
                child = ET.SubElement(element, key)
                child.text = str(value)
    
    def to_string(self, pretty: bool = False) -> str:
        """Convert the XML tree to a string"""
        xml_string = '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(self.root, encoding='unicode')
        if pretty:
            # Pretty-print the XML (requires additional imports)
            import xml.dom.minidom
            xml_string = xml.dom.minidom.parseString(xml_string).toprettyxml()
        return xml_string
    
    def add_item(self, item: ItemModel):
        """Add an Item element from an ItemModel"""
        item_dict = item.model_dump(exclude_none=True)
        self._dict_to_xml(self.root, "Item", item_dict)
        return self
    
    def item_model_to_xml(item: ItemModel) -> str:
        item_dict = item.model_dump(exclude_none=True)
        return xmltodict.unparse({"Item": item_dict}, pretty=True,full_document=False)

def create_get_item_request(item_id: str) -> str:
    """Create a GetItem request XML"""
    return EbayXmlBuilder("GetItemRequest").add_element("ItemID", item_id).to_string()

def create_add_item_request(item: ItemModel) -> str:
    """Create an AddItem request XML"""
    builder = EbayXmlBuilder("AddItemRequest")
    # Convert item to dict and add to XML
    item_dict = item.model_dump(exclude_none=True)
    builder._dict_to_xml(builder.root, "Item", item_dict)
    return builder.to_string()

def create_revise_item_request(item: ItemModel) -> str:
    """Create a ReviseItem request XML"""
    if not item.ItemID:
        raise ValueError("ItemID is required to revise a listing.")
    
    builder = EbayXmlBuilder("ReviseItemRequest")
    item_dict = item.model_dump(exclude_none=True)
    builder._dict_to_xml(builder.root, "Item", item_dict)
    return builder.to_string()

def create_end_item_request(item_id: str, reason: str = "NotAvailable") -> str:
    """Create an EndItem request XML"""
    return (EbayXmlBuilder("EndItemRequest")
            .add_element("ItemID", item_id)
            .add_element("EndingReason", reason)
            .to_string())

def create_get_items_request(items : List[int], limit: Optional[int] = 100, offset: Optional[int] = 1) -> str:
    """Create a GetItems request XML"""
    builder = EbayXmlBuilder("GetItemRequest")
    for item_id in items:
        builder.add_element("ItemID", item_id)
    builder.add_element("Pagination", {
        "EntriesPerPage": limit,
        "PageNumber": offset
    })
    return builder.to_string()

def create_get_all_items_request(limit: int = 100, offset: int = 1) -> str:
    """Create a GetAllItems request XML"""
    return (EbayXmlBuilder("GetItemRequest")
            .add_element("Pagination", {
                "EntriesPerPage": limit,
                "PageNumber": offset
            })
            .to_string())