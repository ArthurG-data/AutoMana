from fastapi import FastAPI, Request
import time, logging, sys, uuid
#from backend.modules.ebay import routers as ebay_router
from fastapi.middleware.cors import CORSMiddleware
#from backend import api 
from contextlib import asynccontextmanager
from backend.core.settings import get_settings
#for fasvicon
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import FileResponse

from backend.core.logging_config import configure_logging
from backend.core.logging_context import set_request_id


configure_logging()
logger = logging.getLogger(__name__)
# ==========================================
# Application State (FastAPI 0.100+ pattern)
# ==========================================

class AppState:
    def __init__(self):
        """Centralized application state"""
        self.async_db_pool = None
        self.sync_db_pool = None
        self.query_executor = None
        self.error_handler = None
        self.service_manager = None


@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("🚀 Application startup initiated")

    try:
        settings = get_settings()
        from backend.request_handling.ErrorHandler import Psycopg2ExceptionHandler
        from backend.core.QueryExecutor import AsyncQueryExecutor
        from backend.core.database import init_async_pool, close_async_pool, init_sync_pool_with_retry, close_sync_pool    
        from backend.core.service_manager import ServiceManager


        app.state.error_handler = Psycopg2ExceptionHandler()
        app.state.async_db_pool = await init_async_pool(settings)
        app.state.sync_db_pool = await init_sync_pool_with_retry(settings)
        app.state.query_executor = AsyncQueryExecutor(app.state.error_handler)
        app.state.service_manager = await ServiceManager.initialize(
            connection_pool=app.state.async_db_pool,
            query_executor=app.state.query_executor
        )
        yield

    finally:
          # Shutdown (always runs)
        logger.info("🔄 Application shutdown initiated")
        
        if hasattr(app.state, 'service_manager') and app.state.service_manager:
            await ServiceManager.close()
            
        if hasattr(app.state, 'async_db_pool') and app.state.async_db_pool:
            await close_async_pool(app.state.async_db_pool)
        
        if hasattr(app.state, 'sync_db_pool') and app.state.sync_db_pool:
            close_sync_pool(app.state.sync_db_pool)
            
        logger.info("✅ Application shutdown complete")

# ==========================================
# FastAPI Application
# ==========================================
app = FastAPI(
    title='AutoManaApp',
    description='Automated card collection management and sales platform',
    version='0.1.0',
    lifespan=lifespan
)
# ==========================================
# Middleware
# ==========================================
from fastapi.middleware.cors import CORSMiddleware

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS if hasattr(settings, 'ALLOWED_ORIGINS') else ["http://localhost:8080"],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*']
)

@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    set_request_id(request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests and responses"""
    start = time.perf_counter()
    try:
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        logger.info(
            "http_request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "elapsed_ms": int(elapsed * 1000),
            },
        )
        return response
    except Exception:
        elapsed = time.perf_counter() - start
        logger.exception(
            "http_request_failed",
            extra={"method": request.method, "path": request.url.path, "elapsed_ms": int(elapsed * 1000)},
        )
        raise
# ==========================================
# Routes
# ==========================================
from backend.api import api_router

app.include_router(api_router)

@app.get('/', tags=['Root'])
async def root():
    return {
        "message": "Welcome to AutoMana API",
        "version": "0.1.0",
        "docs": "/docs"
    }

@app.get('/health', tags=['Health'])
async def health_check():
    return {'status' : 'healthy'}

FAVICON_PATH = Path(__file__).resolve().parent / "static" / "favicon.ico"

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    if not FAVICON_PATH.exists():
        raise HTTPException(status_code=404, detail="favicon not configured")
    return FileResponse(str(FAVICON_PATH), media_type="image/x-icon")