from automana.core.exceptions.base_exception import ServiceError


class ArticleError(ServiceError):
    """Base class for all article-related exceptions."""
    pass


class ArticleNotFoundError(ArticleError, ValueError):
    """Raised when an article is not found (or not published, for public reads).

    Subclasses ValueError as well so callers/tests that expect a ValueError on a
    missing article continue to work; the router maps it to HTTP 404.
    """
    pass


class ArticleValidationError(ArticleError, ValueError):
    """Raised when an article command has no valid input (mapped to HTTP 400)."""
    pass
