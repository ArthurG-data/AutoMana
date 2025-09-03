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

class SessionInactiveError(SessionError):
    """Raised when a session is inactive"""
    pass
class SessionAccessDeniedError(SessionError):
    """Raised when access to a session is denied"""
    pass

class SessionAlreadyExistsError(SessionError):
    """Raised when a session already exists"""
    pass

class SessionUserNotFoundError(SessionError):
    """Raised when a user is not found for a session"""
    pass

class UserSessionNotFoundError(SessionError):
    """Raised when a user session is not found"""
    pass
