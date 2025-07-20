from typing import Generic, TypeVar, Optional, List, Dict, Any
from pydantic import BaseModel, Field

T = TypeVar('T')
DataT = TypeVar('DataT')

class PaginationInfo(BaseModel):
    count: int
    page: int = 1
    pages: int = 1
    limit: int = 100

class ApiResponse(BaseModel, Generic[DataT]):
    status: str = "success"
    message: Optional[str] = None
    data: Optional[DataT|List[DataT]] = None
    
class PaginatedResponse(ApiResponse[List[DataT]], Generic[DataT]):
    pagination: PaginationInfo