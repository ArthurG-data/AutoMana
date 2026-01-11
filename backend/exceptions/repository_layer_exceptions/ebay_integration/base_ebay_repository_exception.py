from backend.exceptions.repository_layer_exceptions.api_errors import ExternalApiError

class EbayBaseRepositoryError(ExternalApiError):
    """Base class for all eBay repository-related exceptions."""

    def __init__(self, message: str, error_code: str = None, status_code: int = None, error_data: dict = None):
        super().__init__(message, error_code=error_code, status_code=status_code, error_data=error_data)
    def __str__(self):
        return f"EbayBaseRepositoryError(message={self.message}, error_code={self.error_code}, status_code={self.status_code}, error_data={self.error_data})"