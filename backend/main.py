from fastapi import FastAPI, Request
import time, logging
from fastapi.middleware.cors import CORSMiddleware
from backend.modules import  admin, public,internal
from backend.modules.ebay.models.errors import EbayServiceError
from backend.modules.ebay.handlers import ebay_error_handler
from backend.modules.auth.errors import AuthError
from backend.modules.auth.handlers import auth_error_handler
from backend.database.errors import DatabaseError
from backend.database.handlers import psycopg_exception_handler
logging.basicConfig(level=logging.INFO)

with open("README.md", "r", encoding="utf-8") as f:
    readme_content = f.read()

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
    }

)
app.include_router(internal.internal_router)
app.include_router(public.api_router)
app.include_router(admin.admin_router)
origins =[
    'http://localhost',
    'http://localhost:8080'
]

app.add_exception_handler(EbayServiceError, ebay_error_handler)
app.add_exception_handler(DatabaseError, psycopg_exception_handler)
app.add_exception_handler(AuthError, auth_error_handler)

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


