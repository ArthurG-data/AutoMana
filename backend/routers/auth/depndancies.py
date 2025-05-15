from backend.routers.users.models import UserInDB
from fastapi import  Depends
from typing_extensions import Annotated
from backend.shared.dependancies import get_current_active_user
from backend.routers.auth.utils import get_token_from_header_or_cookie

currentActiveUser = Annotated[UserInDB, Depends(get_current_active_user)]
tokenDep = Annotated[ str, Depends(get_token_from_header_or_cookie)]