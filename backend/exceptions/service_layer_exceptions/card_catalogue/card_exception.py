from backend.exceptions.base_exception import ServiceError

class CardCatalogueError(ServiceError):
    """Base class for all card catalogue-related exceptions"""
    pass

class CardInsertError(CardCatalogueError):
    """Raised when card insertion fails"""
    pass
class CardNotFoundError(CardCatalogueError):
    """Raised when a card is not found"""
    pass
class InvalidCardIDError(CardCatalogueError):
    """Raised when an invalid card ID is provided"""
    pass
class CardDeletionError(CardCatalogueError):
    """Raised when card deletion fails"""
    pass
class CardRetrievalError(CardCatalogueError):
    """Raised when card retrieval fails"""
    pass