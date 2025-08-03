from pydantic import BaseModel
from typing import Dict, Any

class RepositoryError(Exception):
    """
    Base exception class for all repository layer errors.
    
    This class provides consistent error handling for all repository operations
    with support for error codes, status codes, and additional error data.
    """
    
    def __init__(
        self, 
        message: str, 
        error_code: str = None, 
        status_code: int = None,
        error_data: Dict[str, Any] = None,
        source_exception: Exception = None
    ):
        """
        Initialize repository exception with detailed error information.
        
        Args:
            message: Human-readable error message
            error_code: Internal error code for this exception (e.g. "DB_CONNECTION_ERROR")
            status_code: HTTP status code (for API integrations)
            error_data: Additional error data for debugging
            source_exception: Original exception that caused this error
        """
        self.error_code = error_code
        self.status_code = status_code
        self.error_data = error_data or {}
        self.source_exception = source_exception
        
        # Create full error message
        full_message = message
        if error_code:
            full_message = f"[{error_code}] {message}"
            
        super().__init__(full_message)
    
    @classmethod
    def from_exception(cls, exception: Exception, message: str = None, **kwargs):
        """
        Create a repository exception from another exception.
        
        Args:
            exception: The source exception
            message: Optional message override (if not provided, uses str(exception))
            **kwargs: Additional arguments for the constructor
            
        Returns:
            A new repository exception that wraps the original
        """
        error_message = message or str(exception)
        return cls(
            message=error_message,
            source_exception=exception,
            **kwargs
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert exception to a dictionary representation.
        
        Returns:
            Dictionary with exception details
        """
        result = {
            "message": str(self),
            "type": self.__class__.__name__,
        }
        
        if self.error_code:
            result["error_code"] = self.error_code
            
        if self.status_code:
            result["status_code"] = self.status_code
            
        if self.error_data:
            result["error_data"] = self.error_data
            
        return result

