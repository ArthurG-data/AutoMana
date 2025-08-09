import importlib, logging
from backend.request_handling.QueryExecutor import QueryExecutor
from typing import Dict, Any, List, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ApiHandler:
    """Handles API requests and service execution with a shared query executor"""
    _instance = None
    _pool = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ApiHandler, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, query_executor: Optional[QueryExecutor] = None):
        if hasattr(self, '_initialized') and self._initialized:
            return
        
        self._query_executor = query_executor
        self._initialized = True
        
        # Service registry - maps service paths to module paths and methods
        self._service_registry = {
            # Auth services
            "auth.auth.login": {
                "module": "backend.new_services.auth.auth_service",
                "function": "login",
                "repositories": ["auth", "session"]
            },
            "auth.session.login": {  # Added for compatibility with existing code
                "module": "backend.new_services.auth.auth_service",
                "function": "login",
                "repositories": ["auth", "session"]
            },
            "auth.session.validate": {
                "module": "backend.new_services.auth.session_service",
                "function": "validate_session",
                "repositories": ["session"]
            },
            # Add more services as needed
        }
        
        # Repository registry - maps repo types to module paths and class names
        self._repository_registry = {
            "auth": ("backend.repositories.auth.auth_repository", "AuthRepository"),
            "session": ("backend.repositories.auth.session_repository", "SessionRepository"),
            # Add other repositories
            "market": ("backend.repositories.shop_meta.market_repository", "MarketRepository"),
            "product": ("backend.repositories.shop_meta.product_repository", "ProductRepository"),
            "collection": ("backend.repositories.shop_meta.collection_repository", "CollectionRepository"),
            "theme": ("backend.repositories.shop_meta.theme_repository", "ThemeRepository"),
            "app": ("backend.repositories.ebay.app_repository", "EbayRepository"),
            "card": ("backend.repositories.card_catalog.card_repository", "CardReferenceRepository"),
            "set": ("backend.repositories.card_catalog.set_repository", "SetReferenceRepository"),
        }
    
    @classmethod
    async def initialize(cls, query_executor: QueryExecutor = None):
        """
        Initialize the singleton instance with dependencies.
        This method should be called during application startup.
        """
        try:
            instance = cls(query_executor)

            if query_executor is not None:
                instance._query_executor = query_executor
            
            # Ensure we have a query executor
            if instance._query_executor is None:
                logger.warning("Query executor not provided")
                
            logger.info("ApiHandler successfully initialized")
            return instance
        except Exception as e:
            logger.error(f"Error initializing ApiHandler: {e}")
            raise

    @classmethod
    async def execute_service(cls, service_path: str, **kwargs):
        if cls._instance is None or not hasattr(cls._instance, '_initialized'):
            logger.warning("ApiHandler not initialized, initializing now")
            await cls.initialize()
        logger.info(f"service_path: {service_path}")
        if cls._instance._query_executor is None:
            logger.warning("Query executor not initialized, initializing now")
        return await cls._instance._execute_service(service_path, **kwargs)


    async def _execute_service(self, service_path: str, **kwargs):
        """Execute a service by path with required repositories"""
        logger.info(f"Executing service: {service_path}")
        
        # Get service configuration
        service_config = self._service_registry.get(service_path)
        if not service_config:
            raise ValueError(f"Service configuration not found for {service_path}")
        
        # Import service module and method
        try:
            module = importlib.import_module(service_config["module"])
            service_method = getattr(module, service_config["function"])
        except (ImportError, AttributeError) as e:
            logger.error(f"Error loading service {service_path}: {e}")
            raise ValueError(f"Service {service_path} not found: {str(e)}")
        
        # Execute within transaction
        try:
            async with self._query_executor.transaction() as conn:
                # Create required repositories
                repositories = {}
                
                # Get repository types needed for this service
                repo_types = service_config.get("repositories", [])
                
                # For backward compatibility, if no repositories specified, 
                # use domain.entity to determine repository
                if not repo_types:
                    parts = service_path.split('.')
                    if len(parts) >= 2:
                        domain, entity = parts[0], parts[1]
                        # Use old repository mapping logic
                        repository = self._get_legacy_repository(domain, entity, conn)
                        result = await service_method(repository=repository, **kwargs)
                        return result
                
                # Create each required repository
                for repo_type in repo_types:
                    if repo_type not in self._repository_registry:
                        raise ValueError(f"Unknown repository type: {repo_type}")
                    
                    module_path, class_name = self._repository_registry[repo_type]
                    module = importlib.import_module(module_path)
                    repo_class = getattr(module, class_name)
                    repositories[f"{repo_type}_repository"] = repo_class(conn, self._query_executor)
                
                # Execute service with repositories and parameters
                result = await service_method(**repositories, **kwargs)
                return result
                
        except Exception as e:
            logger.error(f"Error executing service {service_path}: {e}")
            raise 
    def _get_legacy_repository(self, domain: str, entity: str, conn):
        """Legacy method to get repository by domain and entity"""
        #implement factory later
        repo_map = {
            #the factory folder structure is domain/entity
            "shop_meta.market": "MarketRepository",
            "shop_meta.product": "ProductRepository",
            "shop_meta.collection": "CollectionRepository",
            "shop_meta.theme": "ThemeRepository",
            "ebay.app": "EbayRepository",
            "card_catalog.card": "CardReferenceRepository",
            "card_catalog.set": "SetReferenceRepository",
            "auth.auth": "AuthRepository",
            "auth.session": "SessionRepository",
        }

        repo_key = f"{domain}.{entity}"
        repo_name = repo_map.get(repo_key)

        if not repo_name:
            raise ValueError(f"Repository for {repo_key} not found in repository map")
            
        try:
            module = importlib.import_module(f"backend.repositories.{repo_key}_repository")
            repo_class = getattr(module, repo_name)
            return repo_class(conn, self._query_executor)
        except (ImportError, AttributeError) as e:
            logger.error(f"Error loading repository {repo_name}: {e}")
            raise ValueError(f"Repository {repo_name} not found: {str(e)}")
    
    @classmethod
    async def close(cls):
        """Close all resources held by the handler"""
        if cls._instance is None:
            return
            
        if cls._pool is not None:
            logger.info("Closing ApiHandler database pool")
            try:
                await cls._pool.close()
                cls._pool = None
            except Exception as e:
                logger.error(f"Error closing database pool: {e}")

        cls._instance._query_executor = None
        logger.info("ApiHandler resources closed")
    
    