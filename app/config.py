"""
Centralized application configuration.

Reads settings from environment variables (or a .env file). Defaults to a
local SQLite database so the project runs out-of-the-box without any
external services -- set DATABASE_URL to point at PostgreSQL for a
production-like setup (see docker-compose.yml).
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Secure Order Processing API"
    environment: str = "development"

    # Database
    database_url: str = "sqlite:///./order_api.db"

    # JWT / Auth
    secret_key: str = "CHANGE_ME_IN_PRODUCTION_super_secret_key_please_rotate"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Pagination
    default_page_size: int = 20
    max_page_size: int = 100


settings = Settings()
