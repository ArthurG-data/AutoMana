class DatabaseError(Exception):
    """Base class for database-related errors."""

class QueryExecutionError(DatabaseError):
    def __init__(self, message: str, query: str = "", values: any = None):
        super().__init__(message)
        self.query = query
        self.values = values

class NoResultsFound(DatabaseError):
    """Raised when a query expects data but finds none."""

class ConnectionError(DatabaseError):
    """Raised when a connection is attempted but fails."""

class QueryCreationError(DatabaseError):
    """Raise when a Query creation failes."""