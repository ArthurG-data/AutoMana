from pydantic import BaseModel, Field, EmailStr, model_validator
from typing import Optional
from enum import Enum, auto

class Role(str, Enum):
    admin = "admin"
    system = "system"
    developer = "developer"
    tester = "tester"

class AssignRoleRequest(BaseModel):
    role: Role
    reason : Optional[str] = "Assigned via admin endpoint"
