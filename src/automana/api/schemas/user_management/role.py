from pydantic import BaseModel, Field, EmailStr, field_validator, model_validator, validator
from typing import Optional
from enum import Enum, auto
from datetime import datetime, timezone, timedelta

class Role(str, Enum):
    admin = "admin"
    system = "system"
    developer = "developer"
    tester = "tester"

class AssignRoleRequest(BaseModel):
    role: Role = Field(..., description="Role to assign to the user")
    reason: Optional[str] = Field(
        "Assigned via admin endpoint", 
        max_length=500,
        description="Reason for role assignment"
    )
    expires_at: Optional[datetime] = Field(
        datetime.now(timezone.utc) + timedelta(365),
        description="When the role expires (optional for permanent roles)"
    )
    effective_from: Optional[datetime] = Field(
        datetime.now(timezone.utc),
        description="When the role becomes effective (defaults to now)"
    )
    @field_validator('expires_at')
    @classmethod
    def validate_expires_at(cls, v):
        if v and v <= datetime.now(timezone.utc):
            raise ValueError('Expiration date must be in the future')
        return v
    
    @field_validator('effective_from')
    @classmethod
    def validate_effective_from(cls, v):
        if v and v > datetime.now(timezone.utc) + timedelta(days=365):
            raise ValueError('Effective date cannot be more than 1 year in the future')
        return v