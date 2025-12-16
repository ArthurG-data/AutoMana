from functools import lru_cache
from backend.core.settings import  InternalSettings



@lru_cache
def get_internal_settings()-> InternalSettings:
    return InternalSettings()
