from celery_app.celery_main_app import celery_app
import redis, os, logging
from dotenv import load_dotenv
from datetime import datetime, timedelta
from sqlalchemy import text
from backend.utils_new.auth.auth import get_hash_password, verify_password, create_access_token
import json, asyncio

load_dotenv()

logging.basicConfig(level=logging.INFO)
# Redis client for token caching
redis_client = redis.Redis(host='localhost', port=6379, db=2)

SERVICE_USER_MAPPING = {
    #TO DO: ADD TO database USER CREATION SCRIPT
    'ebay_tasks': {
        'username': 'ebay_service_user',
        'password_env': 'EBAY_SERVICE_PASSWORD'
    },
    'pricing_tasks': {
        'username': 'pricing_service_user',
        'password_env': 'PRICING_SERVICE_PASSWORD'
    },
    'scryfall_tasks': {
        'username': 'scryfall_service_user', 
        'password_env': 'SCRYFALL_SERVICE_PASSWORD'
    },
    'general_tasks': {
        'username': 'celery_task_manager',
        'password_env': 'CELERY_SERVICE_PASSWORD'
    }
}
@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def authenticate_celery_app(self, service_type: str) -> None:
    task_id = self.request.id
    start_time = datetime.utcnow()
    

    service_info = SERVICE_USER_MAPPING.get(service_type)
    if not service_info:
        raise ValueError(f"Unknown service type: {service_type}")
    
    service_username = service_info['username']
    service_password = os.getenv(service_info['password_env'])
    
    if not service_password:
        raise ValueError(f"Password not found in environment for {service_username}")
    
    logging.info(f"Celery authentication task {task_id} started for service: {service_username}")
    

    

    try:
        from backend.repositories.user_management.user_repository import UserRepository
        from celery_app.connection import get_connection
        from backend.request_handling.QueryExecutor import SQLAlchemyQueryExecutor

        with get_connection() as conn:
            query_executor = SQLAlchemyQueryExecutor()
            user_repo = UserRepository(conn, query_executor)
            service_user = user_repo.get_sync(service_username)
            if not service_user:
                raise ValueError(f"User not found: {service_username}")
            if not verify_password(service_password, service_user['hashed_password']):
                raise ValueError(f"Invalid password for user: {service_username}")
            logging.info(f"User {service_username} authenticated successfully.")

        access_token_expires = timedelta(hours=24)
        access_token = create_access_token(
            data={"sub": service_user["username"], "user_id": str(service_user["unique_id"])},
            secret_key=os.getenv("SECRET_KEY"),
            algorithm=os.getenv("ENCRYPT_ALGORITHM"),
            expires_delta=access_token_expires
        )
        
        # Cache token in Redis
        cache_key = f"celery_auth_token:{service_username}"
        token_data = {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_at": (datetime.utcnow() + access_token_expires).isoformat(),
            "user_id": str(service_user['unique_id']),
            "username": service_user['username'],
            "authenticated_at": datetime.utcnow().isoformat()
        }
        
        # Cache for 23 hours
        redis_client.setex(
            cache_key,
            23 * 3600,
            json.dumps(token_data)
        )
        
        logging.info(f"✅ Celery app authenticated successfully for service: {service_username}")
        return {
            "success": True,
            "service_name": service_username,
            "user_id": str(service_user['unique_id'])  ,
            "token_cached": True,
            "expires_at": token_data["expires_at"]
        }
        
    except Exception as e:
        logging.error(f"❌ Celery authentication failed for {service_username}: {str(e)}")
        raise
    
  