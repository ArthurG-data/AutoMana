from fastapi import Request
from fastapi.responses import JSONResponse
from backend.routers.ebay.models.errors import EbayServiceError, InvalidTokenError
import logging

logger = logging.getLogger("ebay")

async def ebay_error_handler(request: Request, exc: EbayServiceError):
    logger.error(f"[eBay Error] {exc}", exc_info=True)
    status_code = 401 if isinstance(exc, InvalidTokenError) else 502
    return JSONResponse(status_code=status_code, content={"detail": str(exc)})