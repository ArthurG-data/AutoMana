from main import celery_app
import redis, os, logging
from dotenv import load_dotenv
from datetime import datetime, timedelta
from sqlalchemy import text
#from backend.utils.auth.auth import get_hash_password, verify_password, create_access_token
import json
#from backend.schemas.logging.Celery_Logger import  CeleryLogger_instance
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
"""
@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3, name='authenticate_celery_app')
def authenticate_celery_app(self, service_type: str) -> None:
    logging.info(f"Starting authentication for service type: {service_type}")
    task_id = self.request.id
    start_time = datetime.utcnow()
    worker_name = self.request.hostname
    queue_name = self.request.delivery_info.get('routing_key') if self.request.delivery_info else None
    task_name = self.name   

    service_info = SERVICE_USER_MAPPING.get(service_type)
    service_username = service_info.get('username') if service_info else None
    service_password = os.getenv(service_info.get('password_env')) if service_info else None
    if not service_info or not service_password:
        message = f"Unknown service type or missing password: {service_type}"
        error =  ValueError(message)
        CeleryLogger_instance.log_task_failure(
            task_id
            , task_name
            , str(error)
            , service_username
            , service_type=service_type
            , worker_name=worker_name
            , queue_name=queue_name
            , start_time=start_time
        )
        raise error
    
    CeleryLogger_instance.log_task_start(
        task_id
        , task_name
        , service_username
        , service_type=service_type
        , worker_name=worker_name
        , queue_name=queue_name
    )
    

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
        
        end_time = datetime.utcnow()
        start_dt = start_time
        duration = (end_time - start_dt).total_seconds()

        result ={
            "success": True,
            "service_name": service_username,
            "token": token_data,
            "duration": duration
        }
    
        CeleryLogger_instance.log_task_success(
            task_id=task_id,
            task_name=task_name,
            user=service_username,
            service_type=service_type,
            worker_name=worker_name,
            queue_name=queue_name,
            start_time=start_time,
        )
        return result       
           
    except Exception as e:
        end_time = datetime.utcnow()
        start_dt = start_time
        duration = (end_time - start_dt).total_seconds()
        
        # Log failure
        CeleryLogger_instance.log_task_failure(
            task_id=task_id,
            task_name=task_name,
            error_message=str(e),
            user=service_username,
            service_type=service_type,
            worker_name=worker_name,
            queue_name=queue_name,
            start_time=start_time,  
            additional_info={"duration": duration}
        )
        raise
    
"""