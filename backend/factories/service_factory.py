from typing import Dict, List, Any, Callable, Optional, Tuple
import importlib
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

class ServiceFactory:
    """Factory for creating and configuring services with their repositories"""
    
    def __init__(self, query_executor):
        self.query_executor = query_executor
        self._service_registry = self._build_service_registry()
    
    @lru_cache(maxsize=32)
    def _build_service_registry(self) -> Dict[str, Dict[str, Any]]:
        """Build the service registry from configuration"""
        return {
            # Auth services
            "auth.login": {
                "service_module": "backend.new_services.auth.auth_service",
                "service_method": "login",
                "repositories": ["auth", "session"]
            },
            "auth.validate_session": {
                "service_module": "backend.new_services.auth.session_service", 
                "service_method": "validate_session",
                "repositories": ["session"]
            },
            "auth.refresh_token": {
                "service_module": "backend.new_services.auth.auth_service",
                "service_method": "refresh_token",
                "repositories": ["auth", "session"]
            },
            
            # Add more service configurations as needed
        }
    
    def _get_repository_class(self, repo_type: str) -> type:
        """Get repository class by type"""
        # Repository type to class mapping
        repo_mapping = {
            "auth": {
                "module": "backend.repositories.auth.auth_repository",
                "class": "AuthRepository"
            },
            "session": {
                "module": "backend.repositories.auth.session_repository",
                "class": "SessionRepository"
            },
            # Add more repository mappings
        }
        
        if repo_type not in repo_mapping:
            raise ValueError(f"Unknown repository type: {repo_type}")
        
        mapping = repo_mapping[repo_type]
        module = importlib.import_module(mapping["module"])
        return getattr(module, mapping["class"])
    
    def get_service_config(self, service_id: str) -> Dict[str, Any]:
        """Get service configuration by ID"""
        if service_id not in self._service_registry:
            raise ValueError(f"Unknown service ID: {service_id}")
        
        return self._service_registry[service_id]
    
    def create_service_method(self, service_id: str) -> Callable:
        """Get the service method function"""
        config = self.get_service_config(service_id)
        
        # Import service module and method
        module = importlib.import_module(config["service_module"])
        service_method = getattr(module, config["service_method"])
        
        return service_method
    
    def create_repositories(self, service_id: str, connection) -> Dict[str, Any]:
        """Create all repositories needed for a service"""
        config = self.get_service_config(service_id)
        repositories = {}
        
        for repo_type in config["repositories"]:
            repo_class = self._get_repository_class(repo_type)
            repositories[f"{repo_type}_repository"] = repo_class(connection, self.query_executor)
            
        return repositories
    
    def get_required_repository_types(self, service_id: str) -> List[str]:
        """Get list of repository types required by a service"""
        config = self.get_service_config(service_id)
        return config["repositories"]