from typing import Annotated, Any
import xmltodict
import xml.etree.ElementTree as ET 
from backend.schemas.app_integration.ebay.listings import  BaseModel,ItemModel

def create_xml_body_get_item(item_id : str):
  xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<GetItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">    
	<ErrorLanguage>en_US</ErrorLanguage>
	<WarningLevel>High</WarningLevel>
      <!--Enter an ItemID-->
  <ItemID>{item_id}</ItemID>
</GetItemRequest>
""" 
  return xml_body

def create_xml_body(
    apiCall: str,
    limit: Annotated[int, "min=1, max=100"] = 10,
    offset: int = 1,
) -> str:
    xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<{apiCall} xmlns="urn:ebay:apis:eBLBaseComponents">    
  <ErrorLanguage>en_US</ErrorLanguage>
  <WarningLevel>High</WarningLevel>
  <ActiveList>
    <Sort>TimeLeft</Sort>
    <Pagination>
      <EntriesPerPage>{limit}</EntriesPerPage>
      <PageNumber>{offset}</PageNumber>
    </Pagination>
  </ActiveList>
</{apiCall}>
"""
    return xml_body

def generate_revise_item_request_xml(item: ItemModel) -> str:
    if not item.ItemID:
        raise ValueError("ItemID is required to revise a listing.")

    item_block = item_model_to_xml(item)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<ReviseItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <ErrorLanguage>en_US</ErrorLanguage>
  <WarningLevel>High</WarningLevel>
  {item_block}
</ReviseItemRequest>"""

def generate_add_item_request_xml(item: ItemModel) -> str:
    item_block = item_model_to_xml(item)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<AddItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <ErrorLanguage>en_US</ErrorLanguage>
  <WarningLevel>High</WarningLevel>
  {item_block}
</AddItemRequest>"""

def generate_end_item_request_xml(item_id: str, reason: str = "NotAvailable") -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<EndItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <ErrorLanguage>en_US</ErrorLanguage>
  <WarningLevel>High</WarningLevel>
  <ItemID>{item_id}</ItemID>
  <EndingReason>{reason}</EndingReason>
</EndItemRequest>"""

def item_model_to_xml(item: ItemModel) -> str:
    item_dict = item.model_dump(exclude_none=True)
    return xmltodict.unparse({"Item": item_dict}, pretty=True,full_document=False)

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
