from backend.schemas.user_management.user import UserInDB
from fastapi import  Depends
from typing_extensions import Annotated

#currentActiveUser = Annotated[UserInDB, Depends(get_current_active_user)]
