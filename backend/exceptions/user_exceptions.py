from backend.exceptions.base_exception import ServiceError

class UserError(ServiceError):
    """Base class for all user-related exceptions"""
    pass

class UserNotFoundError(UserError):
    """Exception raised when a user is not found"""
    pass

class UserAlreadyExistsError(UserError):
    """Exception raised when a user already exists"""
    pass

class UserRepositoryError(UserError):
    """Exception raised for errors in the user repository"""
    pass