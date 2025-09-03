from typing import Generic, TypeVar, Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import uuid4

T = TypeVar('T')
DataT = TypeVar('DataT')

class PaginationInfo(BaseModel):
    limit: int
    offset: int
    total_count: int
    has_next: bool
    has_previous: bool

class ApiResponse(BaseModel, Generic[DataT]):
    success: bool = True
    status: str = "success"
    message: Optional[str] = None
    data: Optional[DataT|List[DataT]] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    
class PaginatedResponse(ApiResponse[List[DataT]], Generic[DataT]):
    pagination: PaginationInfo

class ErrorResponse(BaseModel):
    """Error response"""
    success: bool = False
    error: str
    details: Optional[Dict] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    request_id: str = Field(default_factory=lambda: str(uuid4()))