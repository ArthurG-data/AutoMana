import pytest
import xml.etree.ElementTree as ET
from automana.core.services.app_integration.ebay.xml_utils import (
    generate_upload_site_hosted_pictures_request_xml,
)

def test_upload_xml_has_correct_root():
    xml_str = generate_upload_site_hosted_pictures_request_xml()
    root = ET.fromstring(xml_str)
    assert root.tag.endswith("UploadSiteHostedPicturesRequest")

def test_upload_xml_has_picture_system_version():
    xml_str = generate_upload_site_hosted_pictures_request_xml()
    root = ET.fromstring(xml_str)
    ns = {"eb": "urn:ebay:apis:eBLBaseComponents"}
    elem = root.find("eb:PictureSystemVersion", ns)
    assert elem is not None
    assert elem.text == "2"

def test_upload_xml_has_supersize_picture_set():
    xml_str = generate_upload_site_hosted_pictures_request_xml()
    root = ET.fromstring(xml_str)
    ns = {"eb": "urn:ebay:apis:eBLBaseComponents"}
    elem = root.find("eb:PictureSet", ns)
    assert elem is not None
    assert elem.text == "Supersize"
