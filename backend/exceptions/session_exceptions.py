from backend.exceptions.base_exception import ServiceError

class SessionError(ServiceError):
    """Base class for session-related errors"""
    pass

class InvalidTokenError(SessionError):
    """Raised when a token is invalid"""
    pass

class SessionNotFoundError(SessionError):
    """Raised when a session is not found"""
    pass
class SessionExpiredError(SessionError):
    """Raised when a session has expired"""
    pass
