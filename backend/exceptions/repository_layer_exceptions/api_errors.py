from typing import Any, Dict, Optional
from backend.exceptions.repository_layer_exceptions.base_repository_exception import RepositoryError  # adjust import

class ExternalApiError(RepositoryError):
    """Generic error talking to any external API."""

class ExternalApiConnectionError(ExternalApiError):
    """Network/DNS/timeout/connectivity problems."""

class ExternalApiHttpError(ExternalApiError):
    """Non-2xx HTTP responses."""

class ExternalApiUnauthorizedError(ExternalApiHttpError):
    pass

class ExternalApiForbiddenError(ExternalApiHttpError):
    pass

class ExternalApiNotFoundError(ExternalApiHttpError):
    pass

class ExternalApiRateLimitError(ExternalApiHttpError):
    pass

class ExternalApiMethodNotAllowedError(ExternalApiHttpError):
    pass