from automana.core.framework.registry import ServiceRegistry

#Auth repositories
ServiceRegistry.register_db_repository(
    "auth", "automana.core.repositories.app_integration.ebay.auth_repository", "EbayAuthRepository"
)
ServiceRegistry.register_db_repository(
    "listing_builder",
    "automana.core.repositories.app_integration.ebay.listing_builder_repository",
    "EbayListingBuilderRepository",
)
ServiceRegistry.register_db_repository(
    "listing_actions",
    "automana.core.repositories.app_integration.ebay.listing_actions_repository",
    "EbayListingActionsRepository",
)
ServiceRegistry.register_db_repository(
    "session", "automana.api.repositories.auth.session_repository", "SessionRepository"
)
ServiceRegistry.register_db_repository(
    "password_reset",
    "automana.api.repositories.auth.password_reset_repository",
    "PasswordResetRepository",
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
    "collection", "automana.core.repositories.app_integration.shopify.collection_repository", "ShopifyCollectionRepository"
)
ServiceRegistry.register_db_repository(
    "shopify_pipeline", "automana.core.repositories.app_integration.shopify.pipeline_repository", "ShopifyPipelineRepository"
)

# Integration repositories
ServiceRegistry.register_db_repository(
    "app", "automana.core.repositories.app_integration.ebay.app_repository", "EbayAppRepository"
)
ServiceRegistry.register_db_repository(
    "ebay_sales",
    "automana.core.repositories.app_integration.ebay.sales_repository",
    "EbaySalesRepository",
)
ServiceRegistry.register_db_repository(
    "ebay_scrape",
    "automana.core.repositories.app_integration.ebay.ebay_scrape_repository",
    "EbayScrapeSoldRepository",
)
ServiceRegistry.register_db_repository(
    "price", "automana.core.repositories.app_integration.mtg_stock.price_repository", "PriceRepository"
)

# Pricing Tier repositories
ServiceRegistry.register_db_repository(
    "pricing", "automana.core.repositories.pricing.price_repository", "PricingTierRepository"
)
ServiceRegistry.register_db_repository(
    "fx_rates",
    "automana.core.repositories.pricing.fx_rates_repository",
    "FxRatesRepository",
)
ServiceRegistry.register_db_repository(
    "sealed_pricing",
    "automana.core.repositories.pricing.sealed_pricing_repository",
    "SealedPricingRepository",
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
    "ebay_analytics", "automana.core.repositories.app_integration.ebay.ApiAnalytics_repository", "EbayAnalyticsAPIRepository"
)
ServiceRegistry.register_api_repository(
    "search", "automana.core.repositories.app_integration.ebay.ApiBrowse_repository", "EbayBrowseAPIRepository"
)
ServiceRegistry.register_api_repository(
    "selling", "automana.core.repositories.app_integration.ebay.ApiSelling_repository", "EbaySellingRepository"
)
ServiceRegistry.register_api_repository(
    "ebay_finding", "automana.core.repositories.app_integration.ebay.ApiFinding_repository", "EbayFindingAPIRepository"
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

ServiceRegistry.register_api_repository(
    "open_tcg", "automana.core.repositories.app_integration.open_tcg.ApiOpenTCG_repository", "OpenTCGAPIRepository"
)

ServiceRegistry.register_api_repository(
    "ollama",
    "automana.core.repositories.ai.ollama_repository",
    "OllamaAPIRepository",
)
ServiceRegistry.register_api_repository(
    "shopify_api",
    "automana.core.repositories.app_integration.shopify.ApiShopify_repository",
    "ShopifyAPIRepository",
)

ServiceRegistry.register_api_repository(
    "pricecharting",
    "automana.core.repositories.app_integration.pricecharting.pc_api_repository",
    "PricechartingApiRepository",
)

# Storage backends (type → class)
ServiceRegistry.register_storage_backend(
    "local", "automana.core.storage", "LocalStorageBackend"
)

# Named storages (logical name → backend + config)
ServiceRegistry.register_storage("mtgjson",        backend="local", subpath="mtgjson/raw")
ServiceRegistry.register_storage("scryfall",       backend="local", subpath="scryfall/raw_files")
ServiceRegistry.register_storage("errors",         backend="local", subpath="errors/card_import")
ServiceRegistry.register_storage("pricecharting",  backend="local", subpath="pricecharting")
ServiceRegistry.register_storage("shopify",  backend="local", subpath="shopify")
