from dataclasses import dataclass, field
from typing import List, Callable, Optional, Dict
import logging

logger = logging.getLogger(__name__)


@dataclass
class ServiceConfig:
    """Configuration for a registered service.

    Execution knobs
    ───────────────
    `runs_in_transaction` (default True) — ServiceManager wraps the call in an
    explicit asyncpg transaction. Set to False for services whose SQL manages
    its own transaction control (e.g. stored procedures that use internal
    `COMMIT`/`ROLLBACK`). Postgres rejects internal transaction control when
    `CALL` is issued from an atomic block, so those procs must run on a
    non-atomic connection.

    `command_timeout` (default None → inherit Postgres role default) — seconds.
    Applied server-side via `SET [LOCAL|SESSION] statement_timeout` for the
    service's duration. `LOCAL` scope is used inside a transaction (auto-resets
    at COMMIT/ROLLBACK); `SESSION` scope is used when `runs_in_transaction=False`
    and explicitly reset on exit so pooled connections don't leak the override.
    Pass a number of seconds to extend or tighten the ceiling for known-long
    operations (e.g. bulk-ETL procs). None keeps the role's `statement_timeout`
    GUC; there is no way to fully "disable" the timeout — pick a generous
    number instead.
    """
    module: str
    function: str
    db_repositories: List[str] = field(default_factory=list)
    api_repositories: List[str] = field(default_factory=list)
    storage_services: List[str] = field(default_factory=list)
    runs_in_transaction: bool = True
    command_timeout: Optional[float] = None


class ServiceRegistry:
    """
    Central registry for all application services.
    
    Services register themselves using the @register decorator,
    keeping configuration close to the implementation.
    """
    _services: Dict[str, ServiceConfig] = {}
    _repository_registry: Dict[str, tuple[str, str]] = {}
    _api_repository_registry: Dict[str, tuple[str, str]] = {}
    # Backend registry: backend_name → (module, class)
    _storage_backend_registry: Dict[str, tuple[str, str]] = {}
    # Named storage registry: logical_name → {backend: str, **config}
    _storage_registry: Dict[str, dict] = {}
    
    @classmethod
    def register(
        cls,
        path: str,
        db_repositories: List[str] = None,
        api_repositories: List[str] = None,
        storage_services: List[str] = None,
        runs_in_transaction: bool = True,
        command_timeout: Optional[float] = None,
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

        See `ServiceConfig` for the semantics of `runs_in_transaction` and
        `command_timeout`.
        """
        def decorator(func: Callable) -> Callable:
            cls._services[path] = ServiceConfig(
                module=func.__module__,
                function=func.__name__,
                db_repositories=db_repositories or [],
                api_repositories=api_repositories or [],
                storage_services=storage_services or [],
                runs_in_transaction=runs_in_transaction,
                command_timeout=command_timeout,
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
    def register_storage_backend(cls, name: str, module_path: str, class_name: str) -> None:
        """Register a storage backend class (e.g. 'local', 's3')."""
        cls._storage_backend_registry[name] = (module_path, class_name)
        logger.debug(f"Registered storage backend: {name}")

    @classmethod
    def register_storage(cls, name: str, backend: str, **config) -> None:
        """Register a named storage (logical name → backend + config).

        Examples:
            register_storage("scryfall", backend="local", subpath="scryfall/raw_files")
            register_storage("scryfall", backend="s3",    bucket="automana", prefix="scryfall")
        """
        cls._storage_registry[name] = {"backend": backend, **config}
        logger.debug(f"Registered storage: {name} → backend={backend}")

    @classmethod
    def get_db_repository(cls, name: str) -> Optional[tuple[str, str]]:
        """Get DB repository module path and class name"""
        return cls._repository_registry.get(name)

    @classmethod
    def get_api_repository(cls, name: str) -> Optional[tuple[str, str]]:
        """Get API repository module path and class name"""
        return cls._api_repository_registry.get(name)

    @classmethod
    def get_storage_backend(cls, name: str) -> Optional[tuple[str, str]]:
        """Get storage backend (module, class) by backend name."""
        return cls._storage_backend_registry.get(name)

    @classmethod
    def get_storage(cls, name: str) -> Optional[dict]:
        """Get named storage config (includes 'backend' key + backend-specific config)."""
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

# Pricing Tier repositories
ServiceRegistry.register_db_repository(
    "pricing", "automana.core.repositories.pricing.price_repository", "PricingTierRepository"
)

# Ops repositories
ServiceRegistry.register_db_repository(
    "ops", "automana.core.repositories.ops.ops_repository", "OpsRepository"
)
ServiceRegistry.register_db_repository(
    "pipeline_health_snapshot",
    "automana.core.repositories.ops.pipeline_health_snapshot_repository",
    "PipelineHealthSnapshotRepository",
)
ServiceRegistry.register_db_repository(
    "metrics", "automana.core.repositories.metrics_repositories.metrics_repository", "MetricsRepository"
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

# Storage backends (type → class)
ServiceRegistry.register_storage_backend(
    "local", "automana.core.storage", "LocalStorageBackend"
)

# Named storages (logical name → backend + config)
ServiceRegistry.register_storage("mtgjson",  backend="local", subpath="mtgjson/raw")
ServiceRegistry.register_storage("scryfall", backend="local", subpath="scryfall/raw_files")
ServiceRegistry.register_storage("errors",   backend="local", subpath="errors/card_import")

