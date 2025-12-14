import time
print(f"🚀 Starting application at {time.time()}")

from fastapi import FastAPI, Request
import time, logging, sys
#from backend.modules.ebay import routers as ebay_router
from fastapi.middleware.cors import CORSMiddleware
#from backend import api 
from contextlib import asynccontextmanager
from backend.request_handling.ErrorHandler import Psycopg2ExceptionHandler
from backend.request_handling.QueryExecutor import AsyncQueryExecutor
from backend.database.get_database import init_async_pool
from backend.new_services.service_manager import ServiceManager

# Configure root logger to output to console with proper level
for handler in logging.root.handlers:
    logging.root.removeHandler(handler)
    
logging.basicConfig(
    level=logging.DEBUG,  # Try DEBUG level for more verbose output
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)  # Explicitly add console handler
    ]
)

logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("fastapi").setLevel(logging.WARNING)

# For your own loggers
logging.getLogger("backend").setLevel(logging.INFO)  # Or even logging.WARNING
logger = logging.getLogger(__name__)

logger.debug("Logger initialized")

db_pool = None
query_executor = None
error_handler = None
service_manager = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        logger.info("Initializing application resources...")
        #setup ressources

        #create errorhandler
        global error_handler
        error_handler = Psycopg2ExceptionHandler()
        logger.info("Error handler created")
        # Create database pool
        global db_pool
        try:
            db_pool = await init_async_pool()
            logger.info("Database pool created successfully")
        except Exception as e:
            logger.error(f"Failed to create database pool: {e}")
            raise

        # Create query executor with pool and error handler
        global query_executor
        logger.info("Creating query executor...")
        query_executor = AsyncQueryExecutor(error_handler)
        logger.info("Query executor created successfully")
        # Initialize ServiceManager once when the app starts
        logger.info("Initializing ServiceManager...")
        global service_manager
        try:
            service_manager = await ServiceManager.initialize(connection_pool=db_pool, query_executor=query_executor)
            logger.info("ServiceManager initialized successfully")
            
            # Verify initialization worked
            if service_manager.query_executor is None:
                logger.error("ServiceManager query executor is None after initialization!")
                # Fix it by setting directly
                service_manager.query_executor = query_executor
            if service_manager.connection_pool is None:
                logger.error("ServiceManager connection pool is None after initialization!")
                # Fix it by setting directly
                service_manager.connection_pool = db_pool
        except Exception as e:
            logger.error(f"Failed to initialize ServiceManager: {e}")
            raise

        logger.info("Application resources initialized successfully")
    
        yield

        logger.info("Shutting down application resources...")

        try:
            await ServiceManager.close()
            logger.info("ServiceManager closed successfully")
        except Exception as e:
            logger.error(f"Error closing ServiceManager: {e}")

        if db_pool:
            try:
                logger.info("Closing database pool...")
                import asyncio
                try:
            # Wait for pool to close with a timeout
                    await asyncio.wait_for(db_pool.close(), timeout=1.0)
                    logger.info("Database pool closed successfully")
                except asyncio.TimeoutError:
                    logger.warning("Database pool close operation timed out after 5 seconds")
                # Force cleanup anyway
                    db_pool = None
            
            except Exception as e:
                logger.error(f"Error closing database pool: {e}")
                # Force cleanup even if there's an error
                db_pool = None
        
        # Clean up globals
        global_cleanup()
        
        logger.info("Application resources shutdown complete")
    except Exception as e:
        logger.error(f"Error during application lifespan: {e}")
        yield

def global_cleanup():
    """Reset all global instances"""
    global db_pool, query_executor, error_handler, service_manager
    db_pool = None
    query_executor = None
    error_handler = None
    service_manager = None


app = FastAPI(
    title='AutoManaApp',
    summary='Will be a massive app to automanticly manger card collection sale',
    version='0.0.1',
    terms_of_service="http://example.com/terms/",
    contact={
        "name": "Arthur Guillaume",
        "url": "http://x-force.example.com/contact/",
        "email": "todecide@gmail.com",
    },
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
    lifespan=lifespan

)

from backend.api import api_router

app.include_router(api_router)
origins =[
    'http://localhost',
    'http://localhost:8080'
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*']
)

@app.middleware('http')
async def add_process_time_header(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = time.perf_counter() - start_time
    response.headers['X-Process-Time'] = str(process_time)
    return response

app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests and responses"""
    logger.debug(f"Request: {request.method} {request.url}")
    logger.debug(f"Headers: {request.headers}")
    
    # Process the request
    try:
        response = await call_next(request)
        logger.debug(f"Response status: {response.status_code}")
        return response
    except Exception as e:
        logger.error(f"Request failed: {str(e)}")
        raise

@app.get('/')
async def root():
    return {'message' : 'Welcome to the AutoMana API!'}


