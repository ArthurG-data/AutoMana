from pydantic import BaseModel, Field

class HeaderApi(BaseModel):
    site_id: str = Field(default="0", alias="X-EBAY-API-SITEID")
    compatibility_level: str = Field(default="967", alias="X-EBAY-API-COMPATIBILITY-LEVEL")
    call_name: str = Field(default="GetMyeBaySelling", alias="X-EBAY-API-CALL-NAME")
    iaf_token: str = Field(..., alias="X-EBAY-API-IAF-TOKEN")
    class Config:
        populate_by_name = True 




