"""Ingestion pipeline configuration via pydantic-settings.

All values can be overridden through environment variables (case-insensitive)
or a `.env` file in the project root.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the Enjin ingestion service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Redis / Celery ───────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    @property
    def celery_broker_url(self) -> str:
        return self.redis_url

    @property
    def celery_result_backend(self) -> str:
        return self.redis_url

    # ── Neo4j ────────────────────────────────────────────────────────
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme"

    # ── PostgreSQL ───────────────────────────────────────────────────
    postgres_dsn: str = "postgresql+asyncpg://enjin:enjin@localhost:5432/enjin"

    # ── GDELT ────────────────────────────────────────────────────────
    gdelt_base_url: str = "http://data.gdeltproject.org/api/v2"
    gdelt_focus_countries: list[str] = ["DA", "US", "GB", "DE", "FR"]

    # ── External API keys ────────────────────────────────────────────
    news_api_key: str | None = None

    # ── CVR (Danish Business Registry) ───────────────────────────────
    cvr_api_url: str = "https://cvrapi.dk/api"
    cvr_api_key: str | None = None

    # ── Pipeline tuning ──────────────────────────────────────────────
    spacy_model: str = "en_core_web_sm"
    geocoder_user_agent: str = "enjin-osint/0.1 (contact@enjin.dev)"
    geocoder_rate_limit: float = 1.0  # seconds between Nominatim requests

    # ── RSS feed URLs (comma-separated, can be overridden via env) ───
    rss_feed_urls: list[str] = [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "https://www.reutersagency.com/feed/?taxonomy=best-sectors&post_type=best",
    ]


settings = Settings()
