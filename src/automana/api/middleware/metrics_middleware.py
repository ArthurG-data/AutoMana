"""Middleware for capturing API request metrics."""
import time
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from automana.core.metrics.buffer import MetricsBuffer

logger = logging.getLogger(__name__)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Captures request timing and cache hit metrics to MetricsBuffer."""

    def __init__(self, app):
        """Initialize the middleware.

        Args:
            app: The FastAPI/Starlette application instance.
        """
        super().__init__(app)
        self.buffer = MetricsBuffer.get_instance()

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process the request and capture metrics.

        Args:
            request: The incoming request.
            call_next: The next middleware or route handler.

        Returns:
            The response from the next middleware/handler.
        """
        try:
            # Record start time and calculate hour bucket
            start_time = time.time()
            start_hour = int(start_time // 3600)

            # Call the next middleware/handler
            response = await call_next(request)

            # Calculate elapsed time
            elapsed = time.time() - start_time

            # Extract request/response details
            endpoint = request.url.path
            status_code = response.status_code
            is_error = status_code >= 400

            # Extract cache hit flag (default to False if not set)
            is_cache_hit = getattr(request.state, 'cache_hit', False)

            # Add metric to buffer
            self.buffer.add_api_metric(
                hour_key=start_hour,
                endpoint=endpoint,
                status_code=status_code,
                elapsed=elapsed,
                is_error=is_error,
                is_cache_hit=is_cache_hit,
            )

            return response

        except Exception as e:
            # Log the error but don't re-raise (metrics failure shouldn't break the request)
            logger.error(
                "Metrics middleware error",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            raise
