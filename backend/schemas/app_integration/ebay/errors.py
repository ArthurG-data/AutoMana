class EbayServiceError(Exception):
    """Base class for all eBay-related service errors."""
    pass

class InvalidTokenError(EbayServiceError):
    """Raised when an access token is missing or invalid."""
    pass

class ExternalServiceError(EbayServiceError):
    """Raised when eBay's API fails or is unreachable."""
    pass

class EbayParsingError(EbayServiceError):  # Internal
    """Something wrong in your XML parsing logic."""
    pass

class EbayConfigError(EbayServiceError):  # Internal
    """Missing app_id, redirect URI, etc."""
    pass