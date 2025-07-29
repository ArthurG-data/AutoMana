from backend.exceptions.base_exception import ServiceError

class CollectionError(ServiceError):
    """Base class for all collection-related exceptions"""
    pass

class CollectionNotFoundError(CollectionError):
    """Raised when a collection is not found"""
    pass

class CollectionAccessDeniedError(CollectionError):
    """Raised when a user tries to access a collection they don't own"""
    pass

class CollectionCreationError(CollectionError):
    """Raised when collection creation fails"""
    pass

class CollectionUpdateError(CollectionError):
    """Raised when collection update fails"""
    pass

class CollectionDeleteError(CollectionError):
    """Raised when collection deletion fails"""
    pass

class EmptyUpdateError(CollectionError):
    """Raised when trying to update with no fields"""
    pass
class CollectionRetrievalError(CollectionError):
    """Raised when collection retrieval fails"""
    pass

class CollectionEntryError(CollectionError):
    """Base class for collection entry-related exceptions"""
    pass

class EntryNotFoundError(CollectionEntryError):
    """Raised when an entry is not found"""
    pass

class EntryCreationError(CollectionEntryError):
    """Raised when entry creation fails"""
    pass

class EntryUpdateError(CollectionEntryError):
    """Raised when entry update fails"""
    pass

class EntryDeleteError(CollectionEntryError):
    """Raised when entry deletion fails"""
    pass
