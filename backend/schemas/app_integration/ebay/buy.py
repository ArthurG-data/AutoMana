from pydantic import BaseModel, Field
from typing import List, Optional, Literal

class EbayBrowseSearchParams(BaseModel):
    q: Optional[str] = Field(None, description="Keywords to search for")
    gtin: Optional[str] = None
    charity_ids: Optional[List[str]] = None
    fieldgroups: Optional[List[str]] = None
    auto_correct: Optional[str] = None  # Usually "KEYWORD"
    category_ids: Optional[List[str]] = Field(default=None)
    filter: Optional[List[str]] = None  # Each string like "price:[10..50]"
    sort: Optional[
        Literal[
            "price", "-price", "distance", "newlyListed", "endingSoonest"
        ]
    ] = "-price"

    limit: Optional[int] = Field(None, ge=1, le=200)
    offset: Optional[int] = Field(None, ge=0)
    aspect_filter: Optional[str] = None  # Format: "categoryId:123,Color:{Red}"
    epid: Optional[str] = None

    def to_query_params(self) -> dict:
        params = {}

        if self.q:
            params["q"] = self.q
        if self.gtin:
            params["gtin"] = self.gtin
        if self.charity_ids:
            params["charity_ids"] = ",".join(self.charity_ids)
        if self.fieldgroups:
            params["fieldgroups"] = ",".join(self.fieldgroups)
        if self.auto_correct:
            params["auto_correct"] = self.auto_correct
        if self.category_ids:
            params["category_ids"] = ",".join(self.category_ids)
        if self.filter:
            params["filter"] = ",".join(self.filter)
        if self.sort:
            params["sort"] = self.sort
        if self.limit is not None:
            params["limit"] = str(self.limit)
        if self.offset is not None:
            params["offset"] = str(self.offset)
        if self.aspect_filter:
            params["aspect_filter"] = self.aspect_filter
        if self.epid:
            params["epid"] = self.epid

        return params
