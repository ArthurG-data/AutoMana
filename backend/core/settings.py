
from typing_extensions import  Optional, List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
import os
from pathlib import Path

def env_file_path() -> str:
    env = os.getenv("ENV", "dev")
    project_root = Path(__file__).parent.parent.parent 
    return str(project_root / "config" / "env" / f".env.{env}")

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=env_file_path(),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # App env
    env: str = Field(default="dev")  # dev|staging|prod
    DATABASE_URL: str
    ALLOW_DESTRUCTIVE_ENDPOINTS: bool = False
    # Security / JWT
    jwt_secret_key: str = Field(alias="JWT_SECRET_KEY")
    jwt_algorithm: str = "HS256"
    access_token_expiry: int = 30
    encrypt_algorithm: str = "HS256"
    pgp_secret_key: str  = Field(alias="PGP_SECRET_KEY")

    ''' NO NEED BECAUSE url is provided directly
    # Postgres (runtime)
    postgres_host: str
    postgres_db: str
    postgres_user: str
    postgres_password: str
    '''

    # eBay
    ebay_app_id: str | None = None
    ebay_redirect_uri: str | None = None
    ebay_scope: str | None = None  # store as space-separated string in env
    ebay_secret: str | None = None

    # Internal
    internal_api_key: str | None = None
    staging_path: str | None = None
    backend_path: str | None = None
    exchange_app_id: str | None = None

@lru_cache()
def get_settings():
    """Get cached settings"""
    return Settings()
