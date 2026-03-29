from dataclasses import dataclass, field
from typing import List, Callable, Optional, Dict
import logging

logger = logging.getLogger(__name__)


@dataclass
class ServiceConfig:
    """Configuration for a registered service"""
    module: str
    function: str
    db_repositories: List[str] = field(default_factory=list)
    api_repositories: List[str] = field(default_factory=list)
    storage_services: List[str] = field(default_factory=list)


class ServiceRegistry:
    """
    Central registry for all application services.
    
    Services register themselves using the @register decorator,
    keeping configuration close to the implementation.
    """
    _services: Dict[str, ServiceConfig] = {}
    _repository_registry: Dict[str, tuple[str, str]] = {}
    _api_repository_registry: Dict[str, tuple[str, str]] = {}
    _storage_registry: Dict[str, tuple[str, str]] = {}
    
    @classmethod
    def register(
        cls,
        path: str,
        db_repositories: List[str] = None,
        api_repositories: List[str] = None,
        storage_services: List[str] = None
    ) -> Callable:
        """
        Decorator to register a service function.
        
        Usage:
            @ServiceRegistry.register(
                "card_catalog.card.search",
                db_repositories=["card"]
            )
            async def search_cards(card_repository, **kwargs):
                ...
        """
        def decorator(func: Callable) -> Callable:
            cls._services[path] = ServiceConfig(
                module=func.__module__,
                function=func.__name__,
                db_repositories=db_repositories or [],
                api_repositories=api_repositories or [],
                storage_services=storage_services or []
            )
            logger.debug(f"Registered service: {path}")
            return func
        return decorator
    
    @classmethod
    def get(cls, path: str) -> Optional[ServiceConfig]:
        """Get service configuration by path"""
        return cls._services.get(path)
    
    @classmethod
    def all_services(cls) -> Dict[str, ServiceConfig]:
        """Get all registered services"""
        return cls._services.copy()
    
    @classmethod
    def register_db_repository(cls, name: str, module_path: str, class_name: str) -> None:
        """Register a database repository type"""
        cls._repository_registry[name] = (module_path, class_name)
        logger.debug(f"Registered DB repository: {name}")
    
    @classmethod
    def register_api_repository(cls, name: str, module_path: str, class_name: str) -> None:
        """Register an API repository type"""
        cls._api_repository_registry[name] = (module_path, class_name)
        logger.debug(f"Registered API repository: {name}")

    @classmethod
    def register_storage_service(cls, name: str, module_path: str, class_name: str) -> None:
        """Register a storage service type"""
        cls._storage_registry[name] = (module_path, class_name)
        logger.debug(f"Registered storage service: {name}")
    
    @classmethod
    def get_db_repository(cls, name: str) -> Optional[tuple[str, str]]:
        """Get DB repository module path and class name"""
        return cls._repository_registry.get(name)
    
    @classmethod
    def get_api_repository(cls, name: str) -> Optional[tuple[str, str]]:
        """Get API repository module path and class name"""
        return cls._api_repository_registry.get(name)
    
    @classmethod
    def get_storage_service(cls, name: str) -> Optional[tuple[str, str]]:
        """Get storage service module path and class name"""
        return cls._storage_registry.get(name)
    
    @classmethod
    def list_services(cls) -> List[str]:
        """List all registered service paths"""
        return list(cls._services.keys())

#Auth repositories
ServiceRegistry.register_db_repository(
    "auth", "automana.core.repositories.app_integration.ebay.auth_repository", "EbayAuthRepository"
)
ServiceRegistry.register_db_repository(
    "session", "automana.api.repositories.auth.session_repository", "SessionRepository"
)
ServiceRegistry.register_db_repository(
    "user", "automana.api.repositories.user_management.user_repository", "UserRepository"
)
ServiceRegistry.register_db_repository(
    "role", "automana.api.repositories.user_management.role_repository", "RoleRepository"
)

# Card Catalog repositories
ServiceRegistry.register_db_repository(
    "card", "automana.core.repositories.card_catalog.card_repository", "CardReferenceRepository"
)
ServiceRegistry.register_db_repository(
    "set", "automana.core.repositories.card_catalog.set_repository", "SetReferenceRepository"
)
ServiceRegistry.register_db_repository(
    "user_collection", "automana.core.repositories.card_catalog.collection_repository", "CollectionRepository"
)

# Shop Meta repositories
ServiceRegistry.register_db_repository(
    "market", "automana.core.repositories.app_integration.shopify.market_repository", "MarketRepository"
)
ServiceRegistry.register_db_repository(
    "product", "automana.core.repositories.app_integration.shopify.product_repository", "ProductRepository"
)
ServiceRegistry.register_db_repository(
    "collection", "automana.core.repositories.app_integration.shopify.collection_repository", "CollectionRepository"
)

# Integration repositories
ServiceRegistry.register_db_repository(
    "app", "automana.core.repositories.app_integration.ebay.app_repository", "EbayAppRepository"
)
ServiceRegistry.register_db_repository(
    "price", "automana.core.repositories.app_integration.mtg_stock.price_repository", "PriceRepository"
)

ServiceRegistry.register_db_repository(
    "ops", "automana.core.repositories.ops.ops_repository", "OpsRepository"
)

ServiceRegistry.register_db_repository(
    "mtgjson", "automana.core.repositories.app_integration.mtgjson.mtgjson_repository", "MtgjsonRepository"
)

# Analytics repositories
ServiceRegistry.register_db_repository(
    "analytics", "automana.core.repositories.analytics_repositories.analytics_repository", "AnalyticsRepository"
)
# API repositories
ServiceRegistry.register_api_repository(
    "auth_oauth", "automana.core.repositories.app_integration.ebay.ApiAuth_repository", "EbayAuthAPIRepository"
)
ServiceRegistry.register_api_repository(
    "search", "automana.core.repositories.app_integration.ebay.ApiBrowse_repository", "EbayBrowseAPIRepository"
)
ServiceRegistry.register_api_repository(
    "selling", "automana.core.repositories.app_integration.ebay.ApiSelling_repository", "EbaySellingRepository"
)
ServiceRegistry.register_api_repository(
    "mtg_stock", "automana.core.repositories.app_integration.mtg_stock.ApiMtgStock_repository", "ApiMtgStockRepository"
)

ServiceRegistry.register_api_repository(
    "scryfall", "automana.core.repositories.app_integration.scryfall.ApiScryfall_repository", "ScryfallAPIRepository"
)

ServiceRegistry.register_api_repository(
    "mtgjson", "automana.core.repositories.app_integration.mtgjson.Apimtgjson_repository", "ApimtgjsonRepository"
)

ServiceRegistry.register_storage_service(
    "local_storage", "automana.core.storage", "LocalStorageBackend"
)