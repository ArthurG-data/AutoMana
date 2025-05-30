from typing import Annotated

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