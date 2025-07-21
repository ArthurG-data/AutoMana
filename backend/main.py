from fastapi import FastAPI, Request
import time, logging, sys
#from backend.modules.ebay import routers as ebay_router
from fastapi.middleware.cors import CORSMiddleware
from backend import api 
from contextlib import asynccontextmanager
from backend.request_handling.ApiHandler import ApiHandler
from backend.request_handling.ErrorHandler import Psycopg2ExceptionHandler
from backend.request_handling.QueryExecutor import AsyncQueryExecutor
from backend.database.get_database import init_async_pool

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

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG) 

logger.debug("Logger initialized")

with open("README.md", "r", encoding="utf-8") as f:
    readme_content = f.read()

db_pool = None
query_executor = None
error_handler = None
api_handler = None

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
        query_executor = AsyncQueryExecutor(db_pool, error_handler)
        logger.info("Query executor created successfully")
        # Initialize ApiHandler once when the app starts
        logger.info("Initializing ApiHandler...")
        try:
            await ApiHandler.initialize(query_executor=query_executor)
            logger.info("ApiHandler initialized successfully")
            
            # Verify initialization worked
            handler = ApiHandler()
            if handler._query_executor is None:
                logger.error("ApiHandler query executor is None after initialization!")
                # Fix it by setting directly
                handler._query_executor = query_executor
        except Exception as e:
            logger.error(f"Failed to initialize ApiHandler: {e}")
            raise

        logger.info("Application resources initialized successfully")
    
        yield

        logger.info("Shutting down application resources...")

        try:
            await ApiHandler.close()
            logger.info("ApiHandler closed successfully")
        except Exception as e:
            logger.error(f"Error closing ApiHandler: {e}")

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
    global db_pool, query_executor, error_handler, api_handler
    db_pool = None
    query_executor = None
    error_handler = None
    api_handler = None


app = FastAPI(
    title='AutoManaApp',
    description=readme_content,
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


app.include_router(api.api_router)

app.include_router
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

@app.get('/')
async def root():
    return {'message' : 'Hello World'}


