from backend.schemas.logging.log_schemas import LogEntry, LogLevel, TaskStatus
from datetime import datetime
from typing import Dict, Any
from threading import Lock
import logging, os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
""" TO DO: move to the main file to be created once, similar for celery_task"""

class CeleryLogger:
    def __init__(self, log_file_path : str = None):
        self.lock = Lock()

        try:
            self.log_file_path = Path(log_file_path)
            self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
        except FileNotFoundError:
            default_path = Path(__file__).parent / 'logs' / 'celery_logs.log'
            default_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_file_path = default_path

        self.logger = logging.getLogger("celery_logger")
        self.logger.setLevel(logging.INFO)

        if not self.logger.handlers:
            file_handler = logging.FileHandler(self.log_file_path)
            file_handler.setLevel(logging.INFO)
            
            # Console handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            
            # Formatter
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(formatter)
            console_handler.setFormatter(formatter)
            
            self.logger.addHandler(file_handler)
            self.logger.addHandler(console_handler)

    def log_entry(self, log_entry: LogEntry):
        
        with self.lock:
            try:
                with open(self.log_file_path, 'a', encoding='utf-8') as log_file:
                    log_file.write(log_entry.to_json() + '\n')
                
                # Also log to standard logger
                level_map = {
                    LogLevel.DEBUG: logging.DEBUG,
                    LogLevel.INFO: logging.INFO,
                    LogLevel.WARNING: logging.WARNING,
                    LogLevel.ERROR: logging.ERROR,
                    LogLevel.CRITICAL: logging.CRITICAL
                }
                
                self.logger.log(
                    level_map.get(log_entry.level, logging.INFO),
                    f"[{log_entry.task_id}] {log_entry.message}"
                )
                
            except Exception as e:
                self.logger.error(f"Failed to write log entry: {e}")
    
    def log_task_start(
        self, 
        task_id: str, 
        task_name: str, 
        user: str = None,
        service_type: str = None,
        worker_name: str = None,
        queue_name: str = None,
        additional_info: Dict[str, Any] = None
    ):
        """Log task start"""
        entry = LogEntry(
            timestamp=datetime.utcnow().isoformat(),
            level=LogLevel.INFO,
            message=f"Task {task_name} started",
            task_id=task_id,
            task_name=task_name,
            user=user,
            service_type=service_type,
            worker_name=worker_name,
            queue_name=queue_name,
            status=TaskStatus.STARTED,
            start_time=datetime.utcnow().isoformat(),
            additional_info=additional_info or {}
        )
        self.log_entry(entry)

    def log_task_failure(
        self, 
        task_id: str, 
        task_name: str, 
        error_message: str,
        user: str = None,
        service_type: str = None,
        worker_name: str = None,
        queue_name: str = None,
        start_time: datetime = None,
        additional_info: Dict[str, Any] = None
    ):
        """Log task failure"""
        entry = LogEntry(
            timestamp=datetime.utcnow().isoformat(),
            level=LogLevel.ERROR,
            message=f"Task {task_name} failed: {error_message}",
            task_id=task_id,
            task_name=task_name,
            user=user,
            service_type=service_type,
            worker_name=worker_name,
            queue_name=queue_name,
            status=TaskStatus.FAILED,
            start_time=start_time.isoformat() if start_time else None,
            end_time=datetime.utcnow().isoformat(),
            additional_info=additional_info or {}
        )
        self.log_entry(entry
    )
    def log_task_success(
        self, 
        task_id: str, 
        task_name: str, 
        user: str = None,
        service_type: str = None,
        worker_name: str = None,
        queue_name: str = None,
        start_time: datetime = None,
        additional_info: Dict[str, Any] = None
    ):
        """Log task success"""
        entry = LogEntry(
            timestamp=datetime.utcnow().isoformat(),
            level=LogLevel.INFO,
            message=f"Task {task_name} completed successfully",
            task_id=task_id,
            task_name=task_name,
            user=user,
            service_type=service_type,
            worker_name=worker_name,
            queue_name=queue_name,
            status=TaskStatus.SUCCESS,
            start_time=start_time.isoformat() if start_time else None,
            end_time=datetime.utcnow().isoformat(),
            additional_info=additional_info or {}
        )
        self.log_entry(entry)
    
    def log_task_retry(
        self, 
        task_id: str, 
        task_name: str, 
        retry_count: int,
        user: str = None,
        service_type: str = None,
        worker_name: str = None,
        queue_name: str = None,
        start_time: datetime = None,
        additional_info: Dict[str, Any] = None
    ):
        """Log task retry"""
        entry = LogEntry(
            timestamp=datetime.utcnow().isoformat(),
            level=LogLevel.WARNING,
            message=f"Task {task_name} is being retried (attempt {retry_count})",
            task_id=task_id,
            task_name=task_name,
            user=user,
            service_type=service_type,
            worker_name=worker_name,
            queue_name=queue_name,
            status=TaskStatus.RETRIED,
            start_time=start_time.isoformat() if start_time else None,
            additional_info=additional_info or {}
        )
        self.log_entry(entry)
    
    def log_task_revoked(
        self, 
        task_id: str, 
        task_name: str, 
        user: str = None,
        service_type: str = None,
        worker_name: str = None,
        queue_name: str = None,
        additional_info: Dict[str, Any] = None
    ):
        """Log task revoked"""
        entry = LogEntry(
            timestamp=datetime.utcnow().isoformat(),
            level=LogLevel.WARNING,
            message=f"Task {task_name} was revoked",
            task_id=task_id,
            task_name=task_name,
            user=user,
            service_type=service_type,
            worker_name=worker_name,
            queue_name=queue_name,
            status=TaskStatus.REVOKED,
            additional_info=additional_info or {}
        )
        self.log_entry(entry)
    
    def log_task_pending(
        self, 
        task_id: str, 
        task_name: str, 
        user: str = None,
        service_type: str = None,
        worker_name: str = None,
        queue_name: str = None,
        additional_info: Dict[str, Any] = None
    ):
        """Log task pending"""
        entry = LogEntry(
            timestamp=datetime.utcnow().isoformat(),
            level=LogLevel.INFO,
            message=f"Task {task_name} is pending",
            task_id=task_id,
            task_name=task_name,
            user=user,
            service_type=service_type,
            worker_name=worker_name,
            queue_name=queue_name,
            status=TaskStatus.PENDING,
            additional_info=additional_info or {}
        )
        self.log_entry(entry)

    def log_task_custom(
        self,
        log_entry: LogEntry
    ):
        """Log custom task entry"""
        self.log_entry(log_entry)


CeleryLogger_instance = CeleryLogger(os.getenv('CELERY_LOG_FILE_PATH'))
