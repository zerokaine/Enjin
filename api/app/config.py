"""Application settings backed by environment variables / .env file."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration consumed by every subsystem.

    Values are read from environment variables first, then from a *.env* file
    located next to this module (or the working directory).  The ``env_prefix``
    is intentionally empty so that variable names map 1-to-1 to field names
    (e.g. ``NEO4J_URI`` is **not** used; the env var is literally ``neo4j_uri``
    or its upper-case form thanks to Pydantic's case-insensitive matching).
    """

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -- Neo4j (graph database) -----------------------------------------------
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "enjin_dev"

    # -- PostgreSQL + PostGIS (relational / spatial) --------------------------
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "enjin"
    postgres_user: str = "enjin"
    postgres_password: str = "enjin_dev"

    # -- Redis (cache / pub-sub) ----------------------------------------------
    redis_url: str = "redis://redis:6379/0"

    # -- Meilisearch (full-text search) ---------------------------------------
    meili_url: str = "http://meilisearch:7700"
    meili_master_key: str = "enjin_dev_key"

    # -- API server -----------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # -- Derived helpers ------------------------------------------------------
    @property
    def postgres_dsn(self) -> str:
        """Async SQLAlchemy connection string."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton of the application settings."""
    return Settings()
