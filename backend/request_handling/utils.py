import importlib

def locate_service(service_path: str):
    """
    Locates a service function based on the provided service path.
    
    :param service_path: The path to the service function to be located.
    :return: The service function if found, otherwise None.
    """
    parts = service_path.split('.')
    if len(parts) < 3:
        raise ValueError("Invalid service path format. Expected 'module.submodule.function'. Got '{service_path}'")
    domain = parts[0]
    entity = parts[1]
    method = parts[2]

    domain_map = {
        "shop_meta" : "backend.new_services.shop_data_ingestion",
        "ebay" : "backend.modules.ebay.services",
        "card" : "backend.modules.internal.cards"
    }

    module_path = f"{domain_map[domain]}.{entity}_service"
    try:
        module = importlib.import_module(module_path)
        service_method = getattr(module, method)
        return service_method
    except (ImportError, AttributeError) as e:
        raise ValueError(f"Service {service_path} not found. Error: {e}")
