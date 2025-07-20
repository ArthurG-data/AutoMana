from fastapi import FastAPI, Request
import time, logging
#from backend.modules.ebay import routers as ebay_router
from fastapi.middleware.cors import CORSMiddleware
from backend import api 
from contextlib import asynccontextmanager
from backend.request_handling.ApiHandler import ApiHandler

logging.basicConfig(level=logging.INFO)

with open("README.md", "r", encoding="utf-8") as f:
    readme_content = f.read()

api_handler = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize ApiHandler once when the app starts
    global api_handler
    api_handler = ApiHandler()
    # Initialize any connections or resources
    await api_handler._ensure_query_executor()
    
    yield
    
    # Cleanup when the app shuts down
    pool = getattr(ApiHandler, '_pool', None)
    if pool:
        await pool.close()

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


