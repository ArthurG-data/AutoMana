from fastapi import APIRouter, Query, Depends
from typing import Optional, List
from datetime import datetime
from backend.schemas.logging.log_schemas import LogEntry, LogFilter, create_log_reader, LogReader
from dotenv import load_dotenv
import os


load_dotenv(dotenv_path='../../../.env')

log_router = APIRouter(prefix="/logs", tags=["logs"])

def get_log_reader() -> LogReader:
    """Dependency to get log reader"""
    """
    try:
        log_file_path = os.getenv('CELERY_LOG_FILE_PATH')
        if log_file_path is None:
            raise FileNotFoundError("Log file path not set in environment variables.")
    except FileNotFoundError:
        raise
    """    
    log_file_path = "G:\\automana\\logs\\celery_app.log"
    return create_log_reader(log_file_path=log_file_path)

@log_router.get("/")
async def get_logs(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    level: Optional[str] = Query(None),
    task_name: Optional[str] = Query(None),
    service_type: Optional[str] = Query(None),
    user_filter: Optional[str] = Query(None, alias="user"),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    log_reader: LogReader = Depends(get_log_reader),
    #TO DO: current_user: User = Depends(verify_admin_user)
):
    """Endpoint to retrieve logs with filtering and search capabilities"""
    filters = LogFilter(
        start_date=start_date,
        end_date=end_date,
        level=level,
        task_name=task_name,
        service_type=service_type,
        user=user_filter,
        status=status,
        limit=limit,
        offset=offset
    )
    logs, total_count = log_reader.read_logs(filters=filters, search_term=search)
    #create log response
    return {
        "logs": [log.model_dump() for log in logs],
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(logs) < total_count
    }
    