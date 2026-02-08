SERVICE_MODULES : dict[str, list[str]]= {
    "backend": [
            "backend.new_services.auth.auth_service",
            "backend.new_services.auth.session_service",
            "backend.new_services.user_management.user_service",
            "backend.new_services.user_management.role_service",
            "backend.new_services.card_catalog.card_service",
            "backend.new_services.card_catalog.set_service",
            "backend.new_services.card_catalog.collection_service",
            "backend.new_services.app_integration.ebay.auth_services",
            "backend.new_services.app_integration.ebay.browsing_services",
            "backend.new_services.app_integration.ebay.selling_services",
            "backend.new_services.ops.pipeline_services",
            "backend.new_services.app_integration.scryfall.data_loader",
            "backend.new_services.app_integration.mtgjson.data_loader",
            
        ],

    "celery": [
            "backend.new_services.card_catalog.card_service",
            "backend.new_services.card_catalog.set_service",
             "backend.new_services.ops.pipeline_services",
            "backend.new_services.app_integration.scryfall.data_loader",
            "backend.new_services.app_integration.mtg_stock.data_loader",
            "backend.new_services.app_integration.mtg_stock.data_staging",
            "backend.new_services.app_integration.mtgjson.mtgjson_service",
            "backend.new_services.analytics.reporting_services"
            "backend.new_services.app_integration.mtgjson.data_loader",
            
        ] ,
    "all" : [
            "backend.new_services.auth.auth_service",
            "backend.new_services.auth.session_service",
            "backend.new_services.user_management.user_service",
            "backend.new_services.user_management.role_service",
            "backend.new_services.card_catalog.card_service",
            "backend.new_services.card_catalog.set_service",
            "backend.new_services.card_catalog.collection_service",
            "backend.new_services.app_integration.ebay.auth_services",
            "backend.new_services.app_integration.ebay.browsing_services",
            "backend.new_services.app_integration.ebay.selling_services", 
            "backend.new_services.app_integration.scryfall.data_loader",
            "backend.new_services.ops.pipeline_services",
            "backend.new_services.app_integration.mtg_stock.data_staging",
            "backend.new_services.analytics.reporting_services",
            "backend.new_services.app_integration.mtgjson.data_loader",
    ]
}