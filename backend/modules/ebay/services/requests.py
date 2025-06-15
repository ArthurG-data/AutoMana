from typing import Annotated
from backend.modules.ebay.models.listings import CardListing, ListingUpdate, ItemModel
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom.minidom import parseString

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

def build_card_listing_xml(card: CardListing, token: str, verify: bool = True) -> str:
    root_tag = "VerifyAddItemRequest" if verify else "AddItemRequest"
    return f"""<?xml version="1.0" encoding="utf-8"?>
<{root_tag} xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{token}</eBayAuthToken>
  </RequesterCredentials>
  <ErrorLanguage>en_US</ErrorLanguage>
  <WarningLevel>High</WarningLevel>
  <Item>
    <Title>{card.title}</Title>
    <Description>{card.description}</Description>
    <PrimaryCategory><CategoryID>{card.category_id}</CategoryID></PrimaryCategory>
    <StartPrice>{card.price:.2f}</StartPrice>
    <CategoryMappingAllowed>true</CategoryMappingAllowed>
    <Country>{card.site}</Country>
    <Currency>USD</Currency>
    <ConditionID>{card.condition_id}</ConditionID>
    <DispatchTimeMax>3</DispatchTimeMax>
    <ListingDuration>GTC</ListingDuration>
    <ListingType>FixedPriceItem</ListingType>
    <PictureDetails><PictureURL>{card.image_url}</PictureURL></PictureDetails>
    <PostalCode>{card.postal_code}</PostalCode>
    <Quantity>1</Quantity>
    <ItemSpecifics>
      <NameValueList><Name>Game</Name><Value>Magic: The Gathering</Value></NameValueList>
      <NameValueList><Name>Language</Name><Value>English</Value></NameValueList>
      <NameValueList><Name>Card Condition</Name><Value>Near Mint</Value></NameValueList>
    </ItemSpecifics>
    <ReturnPolicy>
      <ReturnsAcceptedOption>ReturnsAccepted</ReturnsAcceptedOption>
      <RefundOption>MoneyBack</RefundOption>
      <ReturnsWithinOption>Days_30</ReturnsWithinOption>
      <ShippingCostPaidByOption>Buyer</ShippingCostPaidByOption>
    </ReturnPolicy>
    <ShippingDetails>
      <ShippingType>Flat</ShippingType>
      <ShippingServiceOptions>
        <ShippingServicePriority>1</ShippingServicePriority>
        <ShippingService>USPSFirstClass</ShippingService>
        <ShippingServiceCost>{card.shipping_cost:.2f}</ShippingServiceCost>
      </ShippingServiceOptions>
    </ShippingDetails>
    <Site>{card.site}</Site>
  </Item>
</{root_tag}>
"""

def build_update(updatedItem : ListingUpdate):
   return f"""<?xml version="1.0" encoding="utf-8"?>
<ReviseItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <ErrorLanguage>en_US</ErrorLanguage>
  <WarningLevel>High</WarningLevel>
  <Item>
    <ItemID>{updatedItem.item_id}</ItemID>
    <StartPrice>{updatedItem.price}</StartPrice>
    <PictureDetails>
      <PictureURL>{updatedItem.pictures}</PictureURL>
    </PictureDetails>
  </Item>
</ReviseItemRequest>"""

