from fastapi import FastAPI, Query, Path, Body,HTTPException, Depends, Request
from typing import Annotated, Any
import time, logging
from models import  ObjectName, BaseCard
from authentification import login, get_user, get_current_active_user
from db_models.users import BaseUser, UserInDB, create_user
from database import cursorDep, execute_query
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)

app = FastAPI()

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

@app.get('/objects/{object_name}')
async def get_object(object_name : ObjectName):
    if object_name is ObjectName.cards:
        return {'object_name' : object_name, 'message': 'You will get all the cards'}
    if object_name is ObjectName.sets:
        return {'object_name' : object_name, 'message' : 'You will get all the sets'}
    return {'object_name' : 'Enter a valid object: cards or sets'}

@app.get('/cards/{card_id}', response_model=list[BaseCard] )
async def read_card(card_id : Annotated[str, Path(title='The unique version id of the card to get', min_length=36, max_length=36)],  connection: cursorDep ) -> list[BaseCard] | dict :
    query =  """ SELECT * FROM card_version WHERE card_version_id = %s """ 
    logging.info("🔹 Route handler started!")
    try:
        cards =  execute_query(connection, query, (card_id,), fetch=True)
        if cards:
            return cards
        else :
            raise HTTPException(status_code=404, detail="Card ID not found")
    except Exception as e:
        return {'card-id' : card_id, 'error':str(e)}
    
class CommonQueryParams:
    def __init__ (self, q : str | None=None, skip: Annotated[int, Query(ge=0)] =0, limit: Annotated[int , Query(ge=1, le=50)]= 10):
        self.q = q,
        self.skip = skip,
        self.limit = limit
     
@app.get('/cards/', response_model=list[BaseCard]) 
async def read_card(commons: Annotated[CommonQueryParams, Depends(CommonQueryParams)], connection : cursorDep):
    query = """ SELECT * FROM card_version LIMIT %s OFFSET %s """
    try:
        cards =  execute_query(connection, query, (commons.limit, commons.skip), fetch=True)
        return cards
    except Exception as e:
        return {'error':str(e)}

@app.get('/users/me', response_model=BaseUser)
async def read_user_me(user : Annotated[BaseUser, Depends(get_current_active_user)]):
    return user


@app.post('/users/')
async def add_user( user: UserInDB, connexion: cursorDep):
    return create_user(user, connexion)

@app.post("/token")
async def token_endpoint(auth_data: dict = Depends(login)):
    return auth_data

@app.get('/users/{user_id}', response_model=BaseUser) 
async def user_endpoint(user_data : UserInDB = Depends(get_user)):
    return user_data

@app.get('/')
async def root():
    return {'message' : 'Hello World'}