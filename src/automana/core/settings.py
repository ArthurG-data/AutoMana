from typing import Optional
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from automana.core.secrets import read_secret
from pathlib import Path
from urllib.parse import quote_plus
import os

def env_file_path() -> str | None:
    env = os.getenv("ENV", "dev")
    # 1) Explicit override (best for installed package / containers)
    explicit = os.getenv("AUTOMANA_ENV_FILE")
    if explicit:
        p = Path(explicit).expanduser().resolve()
        return str(p)
     # 2) Candidate locations
    filename = f".env.{env}"
    candidates = [
        Path.cwd() / "config" / "env" / filename,                 # run from project root
        Path(__file__).resolve().parents[3] / "config" / "env" / filename,  # src checkout
    ]

    for p in candidates:
        if p.exists():
            return str(p)
    # 3) Not found, return default (will be ignored)
    return None

def read_db_password(password :str | None = None,
                     password_file: str | None = None,
                     env_password: str | None = None) -> str:

    if password:
        return password
   # 1) explicit file path (from settings/.env)
    if password_file and Path(password_file).exists():
        return Path(password_file).read_text(encoding="utf-8").strip()

    # 2) explicit plaintext password (from settings/.env)
    if env_password:
        return env_password
    candidates = [
        Path.cwd() / "config" / "secrets" / "backend_db_password.txt",
        Path(__file__).resolve().parents[3] / "config" / "secrets" / "backend_db_password.txt",
    ]
    for p in candidates:
        if p.exists():
            return p.read_text(encoding="utf-8").strip()

    
    raise ValueError(
        "Database password not found. Set POSTGRES_PASSWORD_FILE (Docker), "
        "DB_PASSWORD (env var), or pass db_password parameter"
    )  # Or fallback to another method

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
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

    db_password:  Optional[str] = Field(default=None, exclude=True)
    DB_PASSWORD: str | None = None
    DB_PORT: int = Field(default=5432, alias="POSTGRES_PORT")
    DB_NAME: str = Field(default="automana", alias="DB_NAME")
    DB_USER: str = Field(default="app_backend", alias="APP_BACKEND_DB_USER")
    DB_HOST: str = Field(default="localhost", alias="POSTGRES_HOST")
    POSTGRES_PASSWORD_FILE: str | None = None
    POSTGRES_PASSWORD: str | None = None

    # WEB HOOKS
    DISCORD_WEBHOOK_URL: str | None = None

    @model_validator(mode="after")
    def load_db_password(self):
        self.DB_PASSWORD = read_db_password(
            password=self.db_password,
            password_file=self.POSTGRES_PASSWORD_FILE,
            env_password=self.POSTGRES_PASSWORD
        )
        return self
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
    return Settings(_env_file=env_file_path())
