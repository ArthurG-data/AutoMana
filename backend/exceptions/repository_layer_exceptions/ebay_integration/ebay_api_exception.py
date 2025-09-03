from backend.exceptions.repository_layer_exceptions.ebay_integration.base_ebay_repository_exception import EbayBaseRepositoryError

class EbayBuyApiError(EbayBaseRepositoryError):
    """Custom exception for eBay Buy API errors."""

    def __init__(self, message: str, status_code: int = 500, error_data: dict = None):
        super().__init__(message, status_code=status_code, error_data=error_data)

    def __str__(self):
        return f"EbayBuyApiError(status_code={self.status_code}, message={self.message}, error_data={self.error_data})"
    
class EbayBuyApiNotFoundError(EbayBuyApiError):
    """Custom exception for eBay Buy API not found errors."""

    def __init__(self, message: str, status_code: int = 404, error_data: dict = None):
        super().__init__(message, status_code=status_code, error_data=error_data)

    def __str__(self):
        return f"EbayBuyApiNotFoundError(status_code={self.status_code}, message={self.message}, error_data={self.error_data})"
    
class EbayBuyApiConnectionError(EbayBaseRepositoryError):
    """Custom exception for eBay Buy API connection errors."""

    def __init__(self, message: str, status_code: int = 503, error_data: dict = None):
        super().__init__(message, status_code=status_code, error_data=error_data)

    def __str__(self):
        return f"EbayBuyApiConnectionError(status_code={self.status_code}, message={self.message}, error_data={self.error_data})"
    
class EbayBuyApiRepositoryError(EbayBaseRepositoryError):
    """Custom exception for eBay Buy API repository errors."""

    def __init__(self, message: str, status_code: int = 500, error_data: dict = None):
        super().__init__(message, status_code=status_code, error_data=error_data)

    def __str__(self):
        return f"EbayBuyApiRepositoryError(status_code={self.status_code}, message={self.message}, error_data={self.error_data})"
    
class EbayBuyApiUnauthorizedError(EbayBuyApiError):
    """Custom exception for eBay Buy API unauthorized errors."""

    def __init__(self, message: str, status_code: int = 401, error_data: dict = None):
        super().__init__(message, status_code=status_code, error_data=error_data)

    def __str__(self):
        return f"EbayBuyApiUnauthorizedError(status_code={self.status_code}, message={self.message}, error_data={self.error_data})"
    
class EbayBuyApiForbiddenError(EbayBuyApiError):
    """Custom exception for eBay Buy API forbidden errors."""

    def __init__(self, message: str, status_code: int = 403, error_data: dict = None):
        super().__init__(message, status_code=status_code, error_data=error_data)

    def __str__(self):
        return f"EbayBuyApiForbiddenError(status_code={self.status_code}, message={self.message}, error_data={self.error_data})"
    
class EbayBuyApiRateLimitError(EbayBuyApiError):
    """Custom exception for eBay Buy API rate limit errors."""

    def __init__(self, message: str, status_code: int = 429, error_data: dict = None):
        super().__init__(message, status_code=status_code, error_data=error_data)

    def __str__(self):
        return f"EbayBuyApiRateLimitError(status_code={self.status_code}, message={self.message}, error_data={self.error_data})"
    
