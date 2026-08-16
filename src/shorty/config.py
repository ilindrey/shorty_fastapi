"""Application configuration, loaded from environment variables (12-factor style)."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the shorty service."""

    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    database_url: str = Field(
        default='postgresql+asyncpg://admin:pswd3131@postgres:5432/shorty',
        description='Async SQLAlchemy connection string for Postgres.',
    )
    redis_url: str = Field(
        default='redis://redis:6379/0',
        description='Connection string for the redirect cache.',
    )
    session_secret_key: str = Field(
        default='change-me',
        description='Signing key for the anonymous session cookie.',
    )
    postgres_connection_timeout_seconds: float = Field(
        default=5,
        gt=0,
        description='Maximum wait when establishing a Postgres connection.',
    )
    redis_connection_timeout_seconds: float = Field(
        default=5,
        gt=0,
        description='Maximum wait for Redis connection and socket operations.',
    )
    startup_connection_attempts: int = Field(
        default=3,
        ge=1,
        description='Total connection-check attempts for each storage service.',
    )
    startup_connection_retry_delay_seconds: float = Field(
        default=0.5,
        ge=0,
        description='Delay between startup connection-check attempts.',
    )
    link_ttl_days: int = Field(
        default=14,
        gt=0,
        description='How long a link (and its Redis entry) stays alive after creation.',
    )
    cleanup_interval_minutes: int = Field(
        default=60,
        gt=0,
        description='How often the background job purges expired links.',
    )
    cleanup_batch_size: int = Field(
        default=100,
        gt=0,
        description='Maximum expired-link identifiers read in one cleanup page.',
    )
    page_size: int = Field(
        default=10,
        gt=0,
        description='Default number of links per page in the API and the web UI.',
    )

    @property
    def link_ttl_seconds(self) -> int:
        """`link_ttl_days` expressed in seconds, for the Redis TTL."""
        return self.link_ttl_days * 24 * 60 * 60
