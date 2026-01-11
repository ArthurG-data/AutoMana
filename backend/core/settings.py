from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from backend.core.secrets import read_secret
import os
from pathlib import Path
from urllib.parse import quote_plus

def env_file_path() -> str:
    env = os.getenv("ENV", "dev")
    project_root = Path(__file__).parent.parent.parent 
    return str(project_root / "config" / "env" / f".env.{env}")

def read_db_password():
    password_file = os.getenv("POSTGRES_PASSWORD_FILE")
    if password_file and os.path.exists(password_file):
        with open(password_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None  # Or fallback to another method

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=env_file_path(),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # App env
    env: str = Field(default="dev")  # dev|staging|prod
    modules_namespace: str = Field(default="backend", alias="MODULES_NAMESPACE")

    ALLOW_DESTRUCTIVE_ENDPOINTS: bool = False
    # Security / JWT
    jwt_secret_key: Optional[str] = Field(default_factory=lambda: read_secret("jwt_secret_key"))
    jwt_algorithm: str = "HS256"
    access_token_expiry: int = 30
    encrypt_algorithm: str = "HS256"
    pgp_secret_key: Optional[str]  = Field(default_factory=lambda: read_secret("pgp_secret_key"))
    # retry settings
    DB_CONNECT_MAX_ATTEMPTS: int = 10
    DB_CONNECT_BASE_DELAY_SECONDS: float = 0.5
    DB_CONNECT_MAX_DELAY_SECONDS: float = 10.0

    # Database pool settings
    db_pool_min_conn: int = Field(default=1, alias="DB_POOL_MIN_CONN")
    db_pool_max_conn: int = Field(default=4, alias="DB_POOL_MAX_CONN")

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

    DB_PASSWORD: str = Field(default_factory=read_db_password)
    DB_PORT : int = Field(default=5432)
    DB_NAME : str = Field(default="automana", alias="DB_NAME")
    DB_USER : str = Field(default_factory=lambda: os.getenv("POSTGRES_USER", "backend_app"))
    DB_HOST : str = Field(default="localhost", alias="POSTGRES_HOST")

    # WEB HOOKS
    DISCORD_WEBHOOK_URL: str | None = None

    @property
    def DATABASE_URL_ASYNC(self) -> str:
        password = quote_plus(self.DB_PASSWORD)
        return (
        f"postgresql://{self.DB_USER}:{password}"
        f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    )

@lru_cache()
def get_settings():
    """Get cached settings"""
    return Settings()
