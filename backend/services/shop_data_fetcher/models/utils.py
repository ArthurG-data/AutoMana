from enum import Enum
from pydantic import BaseModel
from typing import  Optional

class Status(str, Enum):
    DOWNLOADED = "downloaded"
    STAGED = "staged"
    VALIDATED = "validated"
    LOADED = "loaded"
    ARCHIVED = "archived"
    SKIPPED = "skipped"
    FAILED = "failed"
    RETRYING = "retrying"
    
class LogStatus(BaseModel):
    timestamp : str
    shop : str
    collection : Optional[str]=None
    page : int
    filename : str
    status :  Status

class AvailableShops(str, Enum):
    gg_brisbane = "Good Game - Brisbane"