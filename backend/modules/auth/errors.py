class AuthError(Exception):
    """Base class for application-level auth errors."""


class InvalidCredentialsError(AuthError):
    """Raised when username or password is incorrect."""


class SessionNotFoundError(AuthError):
    """Raised when a session doesn't exist or is invalid."""


class TokenExpiredError(AuthError):
    """Raised when an access or refresh token is expired."""


class SessionCreationError(AuthError):
    """Raised when inserting a new session fails."""


class TokenRotationError(AuthError):
    """Raised when rotating refresh token fails."""

class TokenInvalidError(AuthError):
    pass