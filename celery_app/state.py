from backend.core.settings import get_settings

class CeleryAppState:
    def __init__(self):
        """Centralized application state for Celery"""
        self.async_db_pool = None
        self.async_runner = None
        self.initialized = False
        self.settings = get_settings()

    def mark_initialized(self):
        self.initialized = True