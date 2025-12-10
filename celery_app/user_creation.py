import asyncio
import asyncpg
import os
import uuid
from dotenv import load_dotenv
from connection import get_connection
from sqlalchemy import text
from backend.utils_new.auth.auth import get_hash_password

load_dotenv(dotenv_path="../celery_app/.env")

async def create_service_users():
    service_users = [
        {
            'username': 'celery_task_manager',
            'email': 'celery.tasks@automana.internal',
            'fullname': 'Celery Task Manager Service',
            'password': os.getenv('CELERY_SERVICE_PASSWORD')
        },
        {
            'username': 'ebay_service_user', 
            'email': 'ebay.service@automana.internal',
            'fullname': 'eBay Integration Service',
            'password': os.getenv('EBAY_SERVICE_PASSWORD')
        },
        {
            'username': 'pricing_service_user',
            'email': 'pricing.service@automana.internal', 
            'fullname': 'Pricing Analysis Service',
            'password': os.getenv('PRICING_SERVICE_PASSWORD')
        },
        {
            'username': 'scryfall_service_user',
            'email': 'scryfall.service@automana.internal',
            'fullname': 'Scryfall Data Service',
            'password': os.getenv('SCRYFALL_SERVICE_PASSWORD')
        }
    ]
    with get_connection() as connection:
        for user in service_users:
            hashed_password = get_hash_password(user['password'])
            user['password'] = hashed_password
            sql = """
            SELECT unique_id FROM users WHERE username = :username OR email = :email and hashed_password = :hashed_password
            """
            result = await connection.execute(text(sql), {
                'username': user['username'],
                'email': user['email'],
                'hashed_password': user['password']
            })
            user_id = await result.scalar()
            if user_id:
                print(f"User {user['username']} already exists with ID: {user_id}")
            else:
                print(f"Creating user {user['username']}...")
                # Code to create the user goes here