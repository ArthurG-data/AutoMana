from backend.exceptions.base_exception import ServiceError

class ShopifyCollectionError(ServiceError):
    """Custom exception for Shopify collection errors"""
    pass

class ShopifyCollectionCreationError(ShopifyCollectionError):
    """Exception raised when collection creation fails"""
    def __init__(self, message: str):
        super().__init__(f"Collection creation failed: {message}")  

class ShopifyCollectionRetrievalError(ShopifyCollectionError):
    """Exception raised when collection retrieval fails"""
    def __init__(self, message: str):
        super().__init__(f"Collection retrieval failed: {message}")

class ShopifyCollectionNotFoundError(ShopifyCollectionError):
    """Exception raised when a collection is not found"""
    def __init__(self, message: str):
        super().__init__(f"Collection not found: {message}")    

class ShopifyCollectionAccessDeniedError(ShopifyCollectionError):
    """Exception raised when access to a collection is denied"""
    def __init__(self, message: str):
        super().__init__(f"Access denied to collection: {message}")

class ShopifyCollectionThemeLinkingError(ShopifyCollectionError):
    """Exception raised when linking a collection to a theme fails"""
    def __init__(self, message: str):
        super().__init__(f"Linking collection to theme failed: {message}")