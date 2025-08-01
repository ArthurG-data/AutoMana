from pydantic import BaseModel
from uuid import UUID

class NewEbayApp(BaseModel):
    app_id: str
    redirect_uri: str
    response_type: str
    secret: str # shoulf be encrypted

class AssignScope(BaseModel):
    scope: str
    app_id: str
    user_id: UUID  # Assuming user_id is a string, adjust as necessary
   