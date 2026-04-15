"""
Application Configuration

Centralized configuration management for the BenGER API application.
"""

import os
from typing import Optional

try:
    from pydantic_settings import BaseSettings
except ImportError:
    # Fallback for older versions
    try:
        from pydantic.v1 import BaseSettings
    except ImportError:
        from pydantic import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Field names are automatically mapped to uppercase environment variables
    by pydantic BaseSettings (e.g. postgres_user -> POSTGRES_USER).
    """

    # Database Configuration
    postgres_user: str = "postgres"
    postgres_password: str = "changeme"
    postgres_db: str = "benger"
    postgres_host: str = "db"
    postgres_port: int = 5432

    # Database URI - prefer DATABASE_URI env var, otherwise construct from components
    database_uri: Optional[str] = None

    @property
    def database_url(self) -> str:
        """Get database URL - prefer DATABASE_URI if available, otherwise construct from components"""
        if self.database_uri:
            return self.database_uri
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    # Redis Configuration - prefer REDIS_URI for production compatibility
    redis_uri: Optional[str] = None
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: Optional[str] = None

    @property
    def redis_url(self) -> str:
        """Get Redis URL - prefer REDIS_URI if available, otherwise construct from components"""
        if self.redis_uri:
            return self.redis_uri

        password_part = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{password_part}{self.redis_host}:{self.redis_port}/0"

    # JWT Configuration
    jwt_secret_key: str = "your-super-secret-key-change-in-production"
    access_token_expire_minutes: int = 60

    # Application Configuration
    environment: str = "development"
    debug: bool = False
    testing: bool = False

    @property
    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.environment.lower() == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment"""
        return self.environment.lower() == "development"

    # Frontend Configuration
    frontend_url: str = "http://localhost:3000"

    # API Configuration
    api_title: str = "BenGER API"
    api_description: str = "BenGER - Benchmark for German Legal Reasoning"
    api_version: str = "3.0.1"

    @property
    def api_root_path(self) -> str:
        """Get API root path from ROOT_PATH env var"""
        return os.getenv("ROOT_PATH", "")

    # CORS Configuration
    cors_origins: list = ["*"]
    cors_allow_credentials: bool = True

    # Cookie Configuration
    cookie_domain: Optional[str] = None  # Set to ".what-a-benger.net" in production

    # Performance Configuration
    default_page_size: int = 30
    max_page_size: int = 100
    debounce_delay_ms: int = 1000
    status_reset_delay_ms: int = 2000
    request_timeout_seconds: int = 30
    max_connections_per_host: int = 100

    # Server Ports
    api_port: int = 8000

    # LLM Configuration
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    deepinfra_api_key: Optional[str] = None

    class Config:
        """Pydantic configuration"""

        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra environment variables


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings instance"""
    return settings
