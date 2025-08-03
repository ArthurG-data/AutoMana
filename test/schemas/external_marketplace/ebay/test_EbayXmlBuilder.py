import pytest
from backend.schemas.external_marketplace.ebay.EbayXmlBuilder import (EbayXmlBuilder
                                                       ,create_add_item_request,
                                                    create_revise_item_request,
                                                    create_end_item_request,
                                                    create_get_item_request
                                                   )

from backend.schemas.app_integration.ebay.listings import ItemModel , BaseCostType    
import xml.etree.ElementTree as ET
from unittest.mock import patch, MagicMock, AsyncMock

@pytest.fixture
def ebay_item_test():
    """Fixture for creating a test eBay item"""
    return ItemModel(
        Title="Test Item",
        Description="Test Description",
        PrimaryCategory={
            "CategoryID": "123",
            "CategoryName": "Test Category"
        },
        StartPrice=BaseCostType(currencyID="USD", value="10.00"),
        Quantity=1,
        ListingDuration="Days_7",
        ItemID="123456789"
    )

class TestEbayXmlBuilder:
    """Test suite for EbayXmlBuilder class"""

    def test_init_creates_root_element(self):
        """Test that the constructor creates a root element with correct name and namespace"""
        builder = EbayXmlBuilder("TestRequest")
        
        assert builder.root.tag == "TestRequest"
        assert builder.root.attrib["xmlns"] == "urn:ebay:apis:eBLBaseComponents"
    
    def test_add_standard_elements(self):
        """Test that standard elements are added to the request"""
        builder = EbayXmlBuilder("TestRequest")
        
        error_lang = builder.root.find("ErrorLanguage")
        warning_level = builder.root.find("WarningLevel")
        
        assert error_lang is not None
        assert error_lang.text == "en_US"
        assert warning_level is not None
        assert warning_level.text == "High"
    
    def test_add_element(self):
        """Test adding a simple element"""
        builder = EbayXmlBuilder("TestRequest")
        builder.add_element("TestElement", "TestValue")
        
        element = builder.root.find("TestElement")
        
        assert element is not None
        assert element.text == "TestValue"
    
    def test_add_element_none_value(self):
        """Test that None values don't create elements"""
        builder = EbayXmlBuilder("TestRequest")
        builder.add_element("TestElement", None)
        
        element = builder.root.find("TestElement")
        
        assert element is None
    
    def test_add_nested_element(self):
        """Test adding a nested element with child elements"""
        builder = EbayXmlBuilder("TestRequest")
        builder.add_nested_element("Parent", {
            "Child1": "Value1",
            "Child2": "Value2"
        })
        
        parent = builder.root.find("Parent")
        
        assert parent is not None
        assert parent.find("Child1").text == "Value1"
        assert parent.find("Child2").text == "Value2"
    
    def test_add_nested_element_none_values(self):
        """Test that None values in nested elements are skipped"""
        builder = EbayXmlBuilder("TestRequest")
        builder.add_nested_element("Parent", {
            "Child1": "Value1",
            "Child2": None
        })
        
        parent = builder.root.find("Parent")
        
        assert parent is not None
        assert parent.find("Child1") is not None
        assert parent.find("Child2") is None
    
    def test_add_item(self, ebay_item_test):
        """Test adding an item from an ItemModel"""
        builder = EbayXmlBuilder("TestRequest")
        builder.add_item(ebay_item_test)

        item_element = builder.root.find("Item")

        assert item_element is not None
        assert item_element.find("Title").text == "Test Item"
        assert item_element.find("Description").text == "Test Description"
        assert item_element.find("PrimaryCategory/CategoryID").text == "123"
        assert item_element.find("Quantity").text == "1"
        assert item_element.find("ListingDuration").text == "Days_7"
        assert item_element.find("ItemID").text == "123456789"
    
    def test_to_string(self):
        """Test converting the XML to a string"""
        builder = EbayXmlBuilder("TestRequest")
        builder.add_element("TestElement", "TestValue")
        
        xml_string = builder.to_string()
        
        assert '<?xml version="1.0" encoding="utf-8"?>' in xml_string
        assert '<TestRequest xmlns="urn:ebay:apis:eBLBaseComponents">' in xml_string
        assert '<ErrorLanguage>en_US</ErrorLanguage>' in xml_string
        assert '<WarningLevel>High</WarningLevel>' in xml_string
        assert '<TestElement>TestValue</TestElement>' in xml_string
    
    def test_dict_to_xml_complex_structure(self):
        """Test converting a complex dictionary to XML"""
        builder = EbayXmlBuilder("TestRequest")
        data = {
            "SimpleValue": "test",
            "NestedObject": {
                "Child1": "value1",
                "Child2": "value2"
            },
            "ArrayOfValues": ["item1", "item2"],
            "ArrayOfObjects": [
                {"id": "1", "name": "First"},
                {"id": "2", "name": "Second"}
            ]
        }
        
        # Access the private method for testing
        builder._dict_to_xml(builder.root, "TestData", data)
        
        test_data = builder.root.find("TestData")
        
        assert test_data.find("SimpleValue").text == "test"
        assert test_data.find("NestedObject/Child1").text == "value1"
        assert test_data.find("NestedObject/Child2").text == "value2"
        
        array_values = test_data.findall("ArrayOfValues")
        assert len(array_values) == 2
        assert array_values[0].text == "item1"
        assert array_values[1].text == "item2"
        
        array_objects = test_data.findall("ArrayOfObjects")
        assert len(array_objects) == 2
        assert array_objects[0].find("id").text == "1"
        assert array_objects[0].find("name").text == "First"
        assert array_objects[1].find("id").text == "2"
        assert array_objects[1].find("name").text == "Second"


class TestXmlRequestFactories:
    """Test suite for XML request factory functions"""
    
    def test_create_get_item_request_success(self, get_repo, ebay_item_test):
        """Test creating a GetItem request"""
        get_repo.return_value = ebay_item_test
        item_id = "123456789"
        xml = create_get_item_request(item_id)

        assert '<GetItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">' in xml
        assert f'<ItemID>{item_id}</ItemID>' in xml


    def test_create_add_item_request_success(self, ebay_item_test):
        """Test creating an AddItem request"""
       
        xml = create_add_item_request(ebay_item_test)
        
        assert '<AddItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">' in xml
        assert '<Title>Test Item</Title>' in xml
        assert '<Description>Test Description</Description>' in xml

    def test_create_revise_item_request_success(self, ebay_item_test):
        """Test creating a ReviseItem request"""
        xml = create_revise_item_request(ebay_item_test)
        
        assert '<ReviseItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">' in xml
        assert '<ItemID>123456789</ItemID>' in xml
    
 
    def test_create_end_item_request(self):
        """Test creating an EndItem request"""
        xml = create_end_item_request("123456789", "NotAvailable")
        
        assert '<EndItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">' in xml
        assert '<ItemID>123456789</ItemID>' in xml
        assert '<EndingReason>NotAvailable</EndingReason>' in xml


# Test XML handling of special characters
def test_xml_escaping():
    """Test that special XML characters are properly escaped"""
    builder = EbayXmlBuilder("TestRequest")
    special_chars = "Item with <tags> & 'quotes' and \"double quotes\""
    builder.add_element("Description", special_chars)
    
    xml = builder.to_string()
    
    # Parse the XML to verify it's valid
    root = ET.fromstring(xml)
    
    namespace = "urn:ebay:apis:eBLBaseComponents"
    desc = root.find(f".//{{{namespace}}}Description")
    
    assert desc is not None
    assert desc.text == special_chars  # ElementTree handles the escaping