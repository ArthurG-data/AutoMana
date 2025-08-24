from backend.exceptions.base_exception import ServiceError

class EbayAuthException(ServiceError):
    """Exception raised for errors in the eBay authentication process."""
    pass

class EbayTokenExchangeException(ServiceError):
    """Exception raised for errors during the token exchange process with eBay."""
    pass

class EbayAppRegistrationException(ServiceError):
    """Exception raised for errors during the eBay app registration process."""
    pass
class EbayAppAssignmentException(ServiceError):
    """Exception raised for errors when assigning an eBay app to a user."""
    pass    
class EbayScopeAssignmentException(ServiceError):
    """Exception raised for errors when assigning a scope to an eBay app."""
    pass
class EbayAppNotFoundException(ServiceError):
    """Exception raised when an eBay app is not found."""
    pass

class EbayAccessTokenException(ServiceError):
    """Exception raised for errors related to eBay access tokens."""
    pass

class EbaySearchError(ServiceError):
    """Exception raised for errors during eBay item searches."""
    pass

class EbayEnvironmentException(ServiceError):
    """Exception raised for errors related to eBay environments."""
    pass