import importlib
import logging
from multiprocessing import pool
from typing import Dict, Any, List, Optional

from fastapi.concurrency import asynccontextmanager

from backend.request_handling.QueryExecutor import QueryExecutor

logger = logging.getLogger(__name__)

class ServiceManager:
    """Singleton class to manage services and their dependencies"""
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ServiceManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, connection_pool, query_executor: Optional[QueryExecutor] = None):
        if hasattr(self, '_initialized') and self._initialized:
            return
            
        self.query_executor = query_executor
        self.connection_pool = connection_pool
        self._initialized = True
        
        # Service registry - maps service paths to module paths and methods
        self._service_registry = {
            # Auth services
            "auth.auth.login": {
                "module": "backend.new_services.auth.auth_service",
                "function": "login",
                "repositories": ["user", "session"]
            },
            "auth.auth.logout": {
                "module": "backend.new_services.auth.auth_service",
                "function": "logout",
                "repositories": ["session"]
            },
            "auth.auth.register": {
                "module": "backend.new_services.user_management.user_service",
                "function": "register",
                "repositories": ["user"]
            },
            "user_management.user.update": {
                "module": "backend.new_services.user_management.user_service",
                "function": "update",
                "repositories": ["user"]
            },
            "user_management.user.search_users": {
                "module": "backend.new_services.user_management.user_service",
                "function": "search_users",
                "repositories": ["user"]
            },
            "user_management.user.delete_user": {
                "module": "backend.new_services.user_management.user_service",
                "function": "delete_user",
                "repositories": ["user"]
            },
            "user_management.user.assign_role" : {
                "module": "backend.new_services.user_management.role_service",
                "function": "assign_role",
                "repositories": ["role"]
            },
            "user_management.user.revoke_role": {
                "module": "backend.new_services.user_management.role_service",
                "function": "revoke_role",
                "repositories": ["role"]
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
            "auth.session.get_user_from_session": {
                "module": "backend.new_services.auth.session_service",
                "function": "get_user_from_session",
                "repositories": [ "session", "user"]
            },
            "auth.session.read": {
                "module": "backend.new_services.auth.session_service",
                "function": "read_session",
                "repositories": ["session"]
            },
            "auth.session.delete": {
                "module": "backend.new_services.auth.session_service",
                "function": "delete_session",
                "repositories": ["session"]
            },
            # Shop Meta services
            "shop_meta.market.get_all": {
                "module": "backend.new_services.shop_data_ingestion.market_service",
                "function": "get_all_markets",
                "repositories": ["market"]
            },
            "shop_meta.market.get": {
                "module": "backend.new_services.shop_data_ingestion.market_service",
                "function": "get_market",
                "repositories": ["market"]
            },
            "shop_meta.market.add": {
                "module": "backend.new_services.shop_data_ingestion.market_service",
                "function": "add_market",
                "repositories": ["market"]
            },
            "shop_meta.collection.add": {
                "module": "backend.new_services.shop_data_ingestion.collection_service",
                "function": "add_collection",
                "repositories": ["collection"]
            },
            "shop_meta.collection.add_many": {
                "module": "backend.new_services.shop_data_ingestion.collection_service",
                "function": "add_many_collections",
                "repositories": ["collection"]
            },
            "shop_meta.theme.add": {
                "module": "backend.new_services.shop_data_ingestion.theme_service",
                "function": "add_theme",
                "repositories": ["theme"]
            },
            "shop_meta.theme.add_collection_theme": {
                "module": "backend.new_services.shop_data_ingestion.theme_service",
                "function": "add_collection_theme",
                "repositories": ["theme", "collection"]
            },
            "shop_meta.product.search": {
                "module": "backend.new_services.shop_data_ingestion.product_service",
                "function": "search_products",
                "repositories": ["product"]
            },
            # Card Catalog services
            "card_catalog.card.search": {
                "module": "backend.new_services.card_catalog.card_service",
                "function": "search_cards",
                "repositories": ["card"]
            },
            "card_catalog.card.add": {
                "module": "backend.new_services.card_catalog.card_service",
                "function": "add",
                "repositories": ["card"]
            },
            "card_catalog.card.add_many": {
                "module": "backend.new_services.card_catalog.card_service",
                "function": "add_many",
                "repositories": ["card"]
            },
            "card_catalog.card.delete": {
                "module": "backend.new_services.card_catalog.card_service",
                "function": "delete_card",
                "repositories": ["card"]
            },
            "card_catalog.set.add" : {
                "module": "backend.new_services.card_catalog.set_service",
                "function": "add_set",
                "repositories": ["set"]
            },
            "card_catalog.set.create_bulk": {
                "module": "backend.new_services.card_catalog.set_service",
                "function": "add_sets_bulk",
                "repositories": ["set"]
            },
            "card_catalog.set.get": {
                "module": "backend.new_services.card_catalog.set_service",
                "function": "get_set",
                "repositories": ["set"]
            },
            "card_catalog.set.list": {
                "module": "backend.new_services.card_catalog.set_service",
                "function": "list_sets",
                "repositories": ["set"]
            },
            "card_catalog.set.delete":{
                "module": "backend.new_services.card_catalog.set_service",
                "function": "delete_set",
                "repositories": ["set"]
            },
            "card_catalog.collection.add": {
                "module": "backend.new_services.card_catalog.collection_service",
                "function": "add_collection",
                "repositories": ["user_collection"]
            },
            "card_catalog.collection.get": {
                "module": "backend.new_services.card_catalog.collection_service",
                "function": "get_collection",
                "repositories": ["user_collection"]
            },
            "card_catalog.collection.get_many": {
                "module": "backend.new_services.card_catalog.collection_service",
                "function": "get_many_collections",
                "repositories": ["user_collection", "card"]
            },
            "card_catalog.collection.update": {
                "module": "backend.new_services.card_catalog.collection_service",
                "function": "update_collection",
                "repositories": ["user_collection"]
            },
            "card_catalog.collection.delete": {
                "module": "backend.new_services.card_catalog.collection_service",
                "function": "delete_collection",
                "repositories": ["user_collection"]
            },
            "card_catalog.collection.delete_entry": {
                "module": "backend.new_services.card_catalog.collection_service",
                "function": "delete_entry",
                "repositories": ["user_collection"]
            },
            "card_catalog.collection.get_entry": {
                "module": "backend.new_services.card_catalog.collection_service",
                "function": "get_entry",
                "repositories": ["collection", "card"]
            },
            # Ebay services
            "ebay.app.auth": {
                "module": "backend.new_services.app_integration.ebay.auth_service",
                "function": "authenticate",
                "repositories": ["app"]
            },
            
            # Add more services as needed
        }
        
        # Repository registry - maps repo types to module paths and class names
        self._repository_registry = {
            # Auth repositories
            "auth": ("backend.repositories.auth.auth_repository", "AuthRepository"),
            "session": ("backend.repositories.auth.session_repository", "SessionRepository"),
            
            # User Management repositories
            "user": ("backend.repositories.user_management.user_repository", "UserRepository"),
            "role": ("backend.repositories.user_management.role_repository", "RoleRepository"),

            # Shop Meta repositories
            "market": ("backend.repositories.shop_meta.market_repository", "MarketRepository"),
            "product": ("backend.repositories.shop_meta.product_repository", "ProductRepository"),
            "collection": ("backend.repositories.shop_meta.collection_repository", "CollectionRepository"),
            "theme": ("backend.repositories.shop_meta.theme_repository", "ThemeRepository"),
            
            # Integration repositories
            "app": ("backend.repositories.app_integration.app_repository", "EbayRepository"),
            
            # Card Catalog repositories
            "card": ("backend.repositories.card_catalog.card_repository", "CardReferenceRepository"),
            "set": ("backend.repositories.card_catalog.set_repository", "SetReferenceRepository"),
            "user_collection": ("backend.repositories.card_catalog.collection_repository", "CollectionRepository"),
        }

    @asynccontextmanager
    async def _get_connection(self):
        """Get a connection from the pool"""
        async with self.connection_pool.acquire() as connection:
            yield connection

    @asynccontextmanager
    async def transaction(self):
        """Execute operations in a transaction"""
        async with self.connection_pool.acquire() as connection:
            tx = connection.transaction()
            try:
                await tx.start()
                logger.debug("Transaction started")
                yield connection
                await tx.commit()
                logger.debug("Transaction committed")
            except Exception as e:
                await tx.rollback()
                logger.debug("Transaction rolled back")
                raise
            finally:
                await connection.close()

    @classmethod
    async def initialize(cls, connection_pool, query_executor: QueryExecutor = None):
        """Initialize the singleton instance with dependencies"""
        try:
            instance = cls(connection_pool, query_executor)

            if query_executor is not None:
                instance.query_executor = query_executor
                
            if instance.query_executor is None:
                logger.warning("Query executor not provided")
            
            if connection_pool is not None:
                instance.connection_pool = connection_pool

            if instance.connection_pool is None:
                logger.warning("Connection pool not provided")

            logger.info("ServiceManager successfully initialized")
            return instance
        except Exception as e:
            logger.error(f"Error initializing ServiceManager: {e}")
            raise
    
    @classmethod
    async def execute_service(cls, service_path: str, **kwargs):
        """Execute a service by ID with provided parameters"""
        if cls._instance is None or not cls._instance._initialized:
            logger.warning("ServiceManager not initialized, initializing now")
            await cls.initialize()
            
        logger.info(f"Executing service: {service_path}")
        
        if cls._instance.query_executor is None:
            logger.warning("Query executor not initialized")
            
        return await cls._instance._execute_service(service_path, **kwargs)
    
    async def _execute_service(self, service_path: str, **kwargs):
        """Execute a service with its required repositories"""
        # Get service configuration
        service_config = self._service_registry.get(service_path)
        if not service_config:
            # Try to use legacy mapping (domain.entity.method) for backward compatibility
            parts = service_path.split('.')
            if len(parts) >= 3:
                domain, entity, method = parts[0], parts[1], parts[2]
                legacy_path = f"{domain}.{entity}.{method}"
                service_config = self._service_registry.get(legacy_path)
                
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
            async with self.transaction()as conn:
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
                        # Use legacy repository mapping logic
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
                    
                    # Name the repository parameter with the repo_type prefix
                    # This allows services to receive multiple repositories with distinct names
                    repo_param_name = f"{repo_type}_repository"
                    repositories[repo_param_name] = repo_class(conn, self.query_executor)
                
                # Log the repositories being used
                repo_names = ", ".join(repositories.keys())
                logger.info(f"Executing service {service_path} with repositories: {repo_names}")
                
                # Execute service with repositories and parameters
                result = await service_method(**repositories, **kwargs)
                return result
                
        except Exception as e:
            logger.error(f"Error executing service {service_path}: {e}")
            raise
    
    def _get_legacy_repository(self, domain: str, entity: str, conn):
        """Legacy method to get repository by domain and entity"""
        repo_map = {
            # Shop Meta repositories
            "shop_meta.market": "MarketRepository",
            "shop_meta.product": "ProductRepository",
            "shop_meta.collection": "CollectionRepository",
            "shop_meta.theme": "ThemeRepository",
            
            # Integration repositories
            "app_integration.ebay": "EbayRepository",
            "ebay.app": "EbayRepository",  # For backward compatibility
            
            # Card Catalog repositories
            "card_catalog.card": "CardReferenceRepository",
            "card_catalog.set": "SetReferenceRepository",
            "card_catalog.collection": "CollectionRepository",
            
            # Auth repositories
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
            return repo_class(conn, self.query_executor)
        except (ImportError, AttributeError) as e:
            logger.error(f"Error loading repository {repo_name}: {e}")
            raise ValueError(f"Repository {repo_name} not found: {str(e)}")
    
    def register_service(self, service_path: str, module_path: str, function_name: str, 
                         repository_types: List[str]):
        """Register a new service in the service registry"""
        self._service_registry[service_path] = {
            "module": module_path,
            "function": function_name,
            "repositories": repository_types
        }
        logger.info(f"Registered service: {service_path}")
        
    def register_repository(self, repo_type: str, module_path: str, class_name: str):
        """Register a new repository in the repository registry"""
        self._repository_registry[repo_type] = (module_path, class_name)
        logger.info(f"Registered repository type: {repo_type}")
    
    @classmethod
    async def close(cls):
        """Close all resources held by the manager"""
        if cls._instance is None:
            return
            
        cls._instance.query_executor = None
        cls._instance._initialized = False
        logger.info("ServiceManager resources closed")
