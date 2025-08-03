
from typing_extensions import  Optional, List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class InternalSettings(BaseSettings):
    internal_api_key: str | None
    staging_path: str
    backend_path : str
    exange_app_id : str
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

        
class GeneralSettings(BaseSettings):
    encrypt_algorithm : str
    secret_key : str
    access_token_expiry : int
    
    model_config =  SettingsConfigDict(env_file='.env',  extra="allow")

class PostgreSettings(BaseSettings):
    postgres_host : str
    postgres_password : str
    postgres_db : str
    postgres_user : str
    secret_key : str
    model_config =  SettingsConfigDict(env_file='.env',  extra="allow")

class EbaySettings(BaseSettings):
    app_id : Optional[str] = None
    response_type : Optional[str] = None
    redirect_uri : Optional[str] = None
    encrypt_algorithm : str
    scope : Optional[List[str]] = None
    secret : Optional[str] = None
    access_token_expiry : int =Field(title='The duration in minute of the access token', default=30)
    pgp_secret_key : str
    model_config =  SettingsConfigDict(env_file='.env',
                                         extra="ignore",
                                         env_file_encoding="utf-8",
                                         case_sensitive=False)
    
@lru_cache()
def get_settings():
    """Get cached settings"""
    return EbaySettings()
