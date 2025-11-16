from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import json

class TaskStatus(Enum):
    PENDING = 'pending'
    STARTED = 'started'
    SUCCESS = 'success'
    FAILED = 'failed'
    RETRY = 'retry'
    REVOKED = 'revoked'

class LogLevel(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class LogEntry(BaseModel):
    timestamp: str
    level: LogLevel
    message: str

    task_id: Optional[str] = None
    task_name: Optional[str] = None
    worker_name: Optional[str] = None
    queue_name: Optional[str] = None

    user :str = None
    task_id: str = None
    status: TaskStatus = None
    additional_info: dict = None

    user: Optional[str] = None
    service_type: Optional[str] = None

    status: Optional[str] = None

    duration: Optional[float] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None

    error_type: Optional[str] = None
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None

    request_id: Optional[str] = None
    correlation_id: Optional[str] = None

    additional_info: Dict[str, Any] = Field(default_factory=dict)

    def to_json(self) -> str:
        return self.model_dump_json()
    
    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()