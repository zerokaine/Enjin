"""Tests for ``app.config.Settings`` and ``get_settings``."""

from __future__ import annotations

from unittest.mock import patch

from app.config import Settings, get_settings


def _settings(**overrides) -> Settings:
    """Create Settings without reading .env file, for test isolation."""
    return Settings(_env_file=None, **overrides)


class TestSettingsDefaults:
    """Verify that the default values are sensible development defaults."""

    def test_neo4j_defaults(self) -> None:
        s = _settings()
        assert s.neo4j_uri == "bolt://neo4j:7687"
        assert s.neo4j_user == "neo4j"
        assert s.neo4j_password == "enjin_dev"

    def test_postgres_defaults(self) -> None:
        s = _settings()
        assert s.postgres_host == "postgres"
        assert s.postgres_port == 5432
        assert s.postgres_db == "enjin"
        assert s.postgres_user == "enjin"
        assert s.postgres_password == "enjin_dev"

    def test_redis_default(self) -> None:
        s = _settings()
        assert s.redis_url == "redis://redis:6379/0"

    def test_meilisearch_defaults(self) -> None:
        s = _settings()
        assert s.meili_url == "http://meilisearch:7700"
        assert s.meili_master_key == "enjin_dev_key"

    def test_api_defaults(self) -> None:
        s = _settings()
        assert s.api_host == "0.0.0.0"
        assert s.api_port == 8000


class TestPostgresDsn:
    """Verify the ``postgres_dsn`` derived property."""

    def test_dsn_format(self) -> None:
        s = _settings()
        dsn = s.postgres_dsn
        assert dsn.startswith("postgresql+asyncpg://")
        assert "enjin:enjin_dev" in dsn
        assert "@postgres:5432/enjin" in dsn

    def test_dsn_reflects_custom_values(self) -> None:
        s = _settings(
            postgres_host="myhost",
            postgres_port=5555,
            postgres_db="mydb",
            postgres_user="myuser",
            postgres_password="mypass",
        )
        dsn = s.postgres_dsn
        assert dsn == "postgresql+asyncpg://myuser:mypass@myhost:5555/mydb"


class TestSettingsFromEnvironment:
    """Verify that environment variables override defaults."""

    def test_neo4j_uri_from_env(self) -> None:
        with patch.dict("os.environ", {"NEO4J_URI": "bolt://custom:7687"}, clear=False):
            s = _settings()
            assert s.neo4j_uri == "bolt://custom:7687"

    def test_postgres_port_from_env(self) -> None:
        with patch.dict("os.environ", {"POSTGRES_PORT": "6543"}, clear=False):
            s = _settings()
            assert s.postgres_port == 6543

    def test_redis_url_from_env(self) -> None:
        with patch.dict("os.environ", {"REDIS_URL": "redis://custom:6380/1"}, clear=False):
            s = _settings()
            assert s.redis_url == "redis://custom:6380/1"

    def test_api_port_from_env(self) -> None:
        with patch.dict("os.environ", {"API_PORT": "9000"}, clear=False):
            s = _settings()
            assert s.api_port == 9000

    def test_meili_master_key_from_env(self) -> None:
        with patch.dict("os.environ", {"MEILI_MASTER_KEY": "super_secret"}, clear=False):
            s = _settings()
            assert s.meili_master_key == "super_secret"

    def test_case_insensitive_env_vars(self) -> None:
        """Pydantic Settings should handle case insensitively."""
        with patch.dict("os.environ", {"neo4j_user": "custom_user"}, clear=False):
            s = _settings()
            assert s.neo4j_user == "custom_user"


class TestGetSettings:
    """Verify the cached settings singleton helper."""

    def test_returns_settings_instance(self) -> None:
        get_settings.cache_clear()
        s = get_settings()
        assert isinstance(s, Settings)

    def test_returns_same_instance(self) -> None:
        get_settings.cache_clear()
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
