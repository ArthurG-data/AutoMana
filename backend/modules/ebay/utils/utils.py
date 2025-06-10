from typing import List, Annotated
from fastapi import Depends


scopes = [
    "https://api.ebay.com/oauth/api_scope",
    "https://api.ebay.com/oauth/api_scope/sell.inventory"
]

def get_scopes()->List[str]:
    return scopes

scopeDep = Annotated[List[str], Depends(get_scopes)]