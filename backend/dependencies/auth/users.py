from backend.modules.auth.models import UserInDB
from fastapi import  Depends
from typing_extensions import Annotated
from backend.shared.dependancies import get_current_active_user

currentActiveUser = Annotated[UserInDB, Depends(get_current_active_user)]
