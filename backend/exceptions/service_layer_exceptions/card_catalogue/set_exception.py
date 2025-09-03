from backend.exceptions.base_exception import ServiceError

class SetError(ServiceError):
    """Base class for all set-related exceptions"""
    pass

class SetNotFoundError(SetError):
    """Raised when a set is not found"""
    pass

class SetAccessDeniedError(SetError):
    """Raised when a user tries to access a set they don't own"""
    pass

class SetCreationError(SetError):
    """Raised when set creation fails"""
    pass

class SetUpdateError(SetError):
    """Raised when set update fails"""
    pass

class SetDeleteError(SetError):
    """Raised when set deletion fails"""
    pass
class SetRetrievalError(SetError):
    """Raised when set retrieval fails"""
    pass    

class SetParsingError(SetError):
    """Raised when set parsing from JSON fails"""
    pass

class SetDeletionError(SetError):
    """Raised when set deletion fails"""
    pass

class SetInsertError(SetError):
    """Raised when set insertion fails"""
    pass