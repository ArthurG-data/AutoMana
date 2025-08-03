from backend.exceptions.base_exception import ServiceError

class RoleNotFoundError(ServiceError):
    """Exception raised when a role is not found."""
    def __init__(self, message: str):
        super().__init__(message)

class RoleRepositoryError(ServiceError):
    """Exception raised for errors in the role repository."""
    def __init__(self, message: str):
        super().__init__(message)
class RoleAssignmentError(ServiceError):
    """Exception raised when role assignment fails."""
    def __init__(self, message: str):
        super().__init__(message)

class PermissionNotFoundError(ServiceError):
    """Exception raised when a permission is not found."""
    def __init__(self, message: str):
        super().__init__(message)