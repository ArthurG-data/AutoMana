from enum import Enum
import os
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
    
class LogFilter(BaseModel):
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    task_id : Optional[str] = None
    level: Optional[str] = None
    task_name: Optional[str] = None
    service_type: Optional[str] = None
    user: Optional[str] = None
    status: Optional[str] = None
    limit: int = 100
    offset: int = 0

from pathlib import Path
from typing import List, Optional

class LogReader:
    def __init__(self, log_file_path: str):
        self.log_file_path = Path(log_file_path)
    
    def read_logs(
        self, 
        filters: LogFilter,
        search_term: Optional[str] = None
    ) -> tuple[List[LogEntry], int]:
        """Read and filter logs"""
        logs = []
        total_count = 0
        
        if not self.log_file_path.exists():
            return logs, 0
        
        with open(self.log_file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f):
                try:
                    log_data = json.loads(line.strip())
                    log_entry = LogEntry(**log_data)
                    
                    # Apply filters
                    if not self._matches_filter(log_entry, filters, search_term):
                        continue
                    
                    total_count += 1
                    
                    # Apply pagination
                    if total_count > filters.offset and len(logs) < filters.limit:
                        logs.append(log_entry)
                    
                except (json.JSONDecodeError, ValueError):
                    continue
        
        return logs, total_count
    
    def _matches_filter(
        self, 
        log_entry: LogEntry, 
        filters: LogFilter,
        search_term: Optional[str]
    ) -> bool:
        """Check if log entry matches filters"""
        
        # Date filters
        if filters.start_date:
            log_time = datetime.fromisoformat(log_entry.timestamp)
            if log_time < filters.start_date:
                return False
        
        if filters.end_date:
            log_time = datetime.fromisoformat(log_entry.timestamp)
            if log_time > filters.end_date:
                return False
        
        # Field filters
        if filters.level and log_entry.level != filters.level:
            return False
        
        if filters.task_name and log_entry.task_name != filters.task_name:
            return False
        
        if filters.service_type and log_entry.service_type != filters.service_type:
            return False
        
        if filters.user and log_entry.user != filters.user:
            return False
        
        if filters.status and log_entry.status != filters.status:
            return False
        
        # Search term
        if search_term:
            search_fields = [
                log_entry.message,
                log_entry.task_id,
                log_entry.task_name,
                log_entry.user,
                log_entry.error_message
            ]
            
            if not any(search_term.lower() in str(field).lower() 
                      for field in search_fields if field):
                return False
        
        return True
    
#test the reader

def create_log_reader(log_file_path: Optional[str] = None) -> LogReader:
    try:
        log_file_path = log_file_path
    except FileNotFoundError:
        log_file_path = None
        raise
    return LogReader(log_file_path=log_file_path)
