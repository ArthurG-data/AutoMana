from fastapi import  Depends
from typing_extensions import Annotated
from backend.modules.auth.utils import get_token_from_header_or_cookie

tokenDep = Annotated[ str, Depends(get_token_from_header_or_cookie)]