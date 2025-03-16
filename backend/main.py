from fastapi import FastAPI, Query, Path, Body, Cookie,HTTPException, Response, Form, Depends
from fastapi.responses import JSONResponse
from typing import Annotated, Any
import psycopg2
from psycopg2.extras import RealDictCursor
from models import  ObjectName, BaseCard
from authentification import BaseUser, UserInDB, login, get_current_user,get_user, get_current_active_user

from database import get_cursor



app = FastAPI()


@app.get('/objects/{object_name}')
async def get_object(object_name : ObjectName):
    if object_name is ObjectName.cards:
        return {'object_name' : object_name, 'message': 'You will get all the cards'}
    if object_name is ObjectName.sets:
        return {'object_name' : object_name, 'message' : 'You will get all the sets'}
    return {'object_name' : 'Enter a valid object: cards or sets'}

@app.get('/cards/{card_id}', response_model=BaseCard, )
async def read_card(card_id : Annotated[str, Path(title='The unique version id of the card to get', min_length=36, max_length=36)], cursor: Annotated[psycopg2.extensions.connection, Depends(get_cursor)]) -> BaseCard | dict :
    try:
        cursor.execute(
            """ SELECT * FROM card_version WHERE card_version_id = %s """, (card_id,))
        card = cursor.fetchone()
        if card:
            return card
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
async def read_card(commons: Annotated[CommonQueryParams, Depends(CommonQueryParams)], cursor: Annotated[psycopg2.extensions.connection, Depends(get_cursor)]):
    try:
        cursor.execute(""" SELECT * FROM card_version LIMIT %s OFFSET %s """, (commons.limit, commons.skip))
        cards = cursor.fetchall()
        return cards
    except Exception as e:
        return {'error':str(e)}

@app.get('/users/me')
async def read_user_me(user : BaseUser = Depends(get_current_active_user)):
    return user


@app.post('/users/')
async def create_user(user : Annotated[UserInDB, Body(
    example=[
        {
            'first_name' : 'John',
            'last_name' : 'Doe',
            'username' : 'johnDow',
            'user_id' : 234,
            'email' : 'johndow@gmail.com',
            'password' : 'password',
            'register_date' : 'dd/mm/yyyy'
        }
    ]
)
                                       ]):
    return user

@app.post("/token")
async def token_endpoint(auth_data: dict = Depends(login)):
    return auth_data

@app.get('/users/{user_id}', response_model=BaseUser) 
async def user_endpoint(user_data : UserInDB = Depends(get_user)):
    return user_data

@app.get('/')
async def root():
    return {'message' : 'Hello World'}