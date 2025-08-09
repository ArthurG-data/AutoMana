from functools import lru_cache
from backend.schemas.settings import PostgreSettings, GeneralSettings, EbaySettings, InternalSettings

@lru_cache
def get_db_settings()->PostgreSettings:
    return PostgreSettings()

@lru_cache
def get_general_settings()->GeneralSettings:
    return GeneralSettings()

@lru_cache
def get_ebay_settings()->EbaySettings:
    return EbaySettings()

@lru_cache
def get_internal_settings()-> InternalSettings:
    return InternalSettings()
