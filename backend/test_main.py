from typing import Union
from fastapi.testclient import TestClient
from fastapi import FastAPI, Header, HTTPException, Body
from pydantic import BaseModel
from typing_extensions import Annotated
from .main import app

client = TestClient(app)

fake_secret_token='fake-super-secret-token'

user_1 = {
  "username": "user1",
  "email": "user1@example.com",
  "fullname": "user one",
  "disabled": False,
  "hashed_password": "password1"
}

user_1a = {
  "username": "user1",
  "email": "unew@example.com",
  "fullname": "user weq",
  "disabled": False,
  "hashed_password": "passworde"
}

user_1b = {
  "username": "user4",
  "email": "user1@example.com",
  "fullname": "user weq",
  "disabled": False,
  "hashed_password": "passworde"
}


user_2 = {
  "username": "user2",
  "email": "user2@example.com",
  "fullname": "user two",
  "disabled": True,
  "hashed_password": "password2"
}



def test_read_main():
    response = client.get("/", headers={"X-Token": fake_secret_token})
    assert response.status_code == 200
    assert response.json() == {"message": "Hello World"}

def test_create_user():
    response = client.post('/users/', headers={"X-Token": fake_secret_token}, json=user_1)
    assert response.status_code == 200

def test_user_same_username():
    response = client.post('/users/', headers={"X-Token": fake_secret_token}, json=user_1a)
    assert response.status_code == 400
    assert response.json() == {"detail": "User already exists"}

def test_user_same_email():
    response = client.post('/users/', headers={"X-Token": fake_secret_token}, json=user_1b)
    assert response.status_code == 400
    assert response.json() == {"detail": "User already exists"}


def test_read_user_bad_token():
    response = client.get('/users/user1', headers={"X-Token": 'wrong_token'})
    assert response.status_code == 400
    assert response.json() == {"detail": "X-Token header invalid"}
    
def test_read_user():
    response = client.get('/users/user1', headers={"X-Token": fake_secret_token})
    assert response.status_code == 200


def test_delete_user_not_present ():
    response = client.delete('/users/', headers={"X-Token": fake_secret_token}, params={"usernames": ['bob']}   )
    assert response.status_code == 404

def test_delete_user():
    response = client.delete('/users/', headers={"X-Token": fake_secret_token}, params={"usernames": [user_1.get('username')]}   )
    assert response.status_code == 204
