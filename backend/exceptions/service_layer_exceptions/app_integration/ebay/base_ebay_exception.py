from backend.exceptions.base_exception import ServiceError

class EbayServiceError(ServiceError):
    """Base class for eBay service-related exceptions."""
    
    def __init__(self, message: str, status_code: int = None, error_data: dict = None):
        self.status_code = status_code
        self.error_data = error_data or {}
        super().__init__(message)

    def __str__(self):
        return f"EbayServiceError(status_code={self.status_code}, message={self.message}, error_data={self.error_data})"