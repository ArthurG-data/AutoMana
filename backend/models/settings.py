
from typing_extensions import  Optional, List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    secret_key : str
    model_config =  SettingsConfigDict(env_file='.env',  extra="allow")