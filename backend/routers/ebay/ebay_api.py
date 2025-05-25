from pydantic import BaseModel, Field
from typing import Annotated
import httpx
from psycopg2.extensions import connection

trading_api = "https://api.ebay.com/ws/api.dll"

class HeaderApi(BaseModel):
    site_id: str = Field(default="0", alias="X-EBAY-API-SITEID")
    compatibility_level: str = Field(default="967", alias="X-EBAY-API-COMPATIBILITY-LEVEL")
    call_name: str = Field(default="GetMyeBaySelling", alias="X-EBAY-API-CALL-NAME")
    iaf_token: str = Field(..., alias="X-EBAY-API-IAF-TOKEN")

def create_xml_body(
    apiCall: str,
    limit: Annotated[int, "min=1, max=100"] = 3,
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

async def doPostTradingRequest( xml_body : str, headers: HeaderApi):
     async with httpx.AsyncClient() as client:
        response = await client.post(trading_api, data=xml_body, headers=headers)
        response.raise_for_status()
        return response.text 
