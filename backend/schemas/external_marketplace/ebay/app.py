from pydantic import BaseModel, Field
from uuid import UUID
from typing import Dict, List, Optional, Any
import xmltodict
import xml.etree.ElementTree as ET 

class NewEbayApp(BaseModel):
    app_id: str
    redirect_uri: str
    response_type: str
    secret: str # should be encrypted

class AssignScope(BaseModel):
    scope: str
    app_id: str
    user_id: UUID  # Assuming user_id is a string, adjust as necessary
