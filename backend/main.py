from fastapi import FastAPI, Depends, Request
from typing import Annotated, Any
import time, logging
from backend.authentification import login
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import users, cards


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
app.include_router(users.router)
app.include_router(cards.router)

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



@app.post("/token", tags=['users'])
async def token_endpoint(auth_data: dict = Depends(login)):
    return auth_data


@app.get('/')
async def root():
    return {'message' : 'Hello World'}