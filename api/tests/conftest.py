"""Shared fixtures and mocks for the Enjin API test suite.

Every external service (Neo4j, PostgreSQL, Redis, Meilisearch) is mocked so
that tests can run without any infrastructure.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Mock GraphDB — must be patched BEFORE importing the app
# ---------------------------------------------------------------------------


class FakeGraphDB:
    """In-memory stub that replaces ``app.db.neo4j.GraphDB``."""

    def __init__(self) -> None:
        self.execute = AsyncMock(return_value=[])
        self.find_entity = AsyncMock(return_value=None)
        self.find_connections = AsyncMock(return_value=[])
        self.create_entity = AsyncMock(return_value={"id": "new-entity", "name": "New", "type": "person"})
        self.create_relationship = AsyncMock(return_value={})
        self.search_entities = AsyncMock(return_value=[])
        self.connect = AsyncMock()
        self.close = AsyncMock()


class FakeSearchClient:
    """In-memory stub that replaces ``app.db.search.SearchClient``."""

    ENTITIES_INDEX = "entities"
    EVENTS_INDEX = "events"

    def __init__(self) -> None:
        self.client = MagicMock()
        self.search = MagicMock(return_value={"hits": [], "estimatedTotalHits": 0, "processingTimeMs": 0})
        self.index_entity = MagicMock()
        self.index_entities = MagicMock()
        self.index_event = MagicMock()
        self.index_events = MagicMock()
        self.init_indexes = MagicMock()
        self.connect = MagicMock()
        self.close = MagicMock()


class FakeAsyncSession:
    """Mimics an async SQLAlchemy session for tests."""

    def __init__(self, results: Any = None) -> None:
        self._results = results
        self.add = MagicMock()
        self.flush = AsyncMock()
        self.refresh = AsyncMock()
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.execute = AsyncMock(return_value=self._make_result())

    def _make_result(self) -> MagicMock:
        result = MagicMock()
        result.scalar_one_or_none.return_value = self._results
        result.scalars.return_value.all.return_value = (
            self._results if isinstance(self._results, list) else []
        )
        result.scalar.return_value = 0
        return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_graph_db() -> FakeGraphDB:
    """Return a fresh ``FakeGraphDB`` instance."""
    return FakeGraphDB()


@pytest.fixture()
def fake_search_client() -> FakeSearchClient:
    """Return a fresh ``FakeSearchClient`` instance."""
    return FakeSearchClient()


@pytest.fixture()
def fake_session() -> FakeAsyncSession:
    """Return a fresh ``FakeAsyncSession`` instance."""
    return FakeAsyncSession()


# ---------------------------------------------------------------------------
# Sample entities
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_person_data() -> dict[str, Any]:
    return {
        "id": "person-001",
        "name": "Jane Doe",
        "type": "person",
        "role": "CEO",
        "nationality": "US",
        "aliases": ["J. Doe"],
        "metadata": {"source": "test"},
    }


@pytest.fixture()
def sample_organization_data() -> dict[str, Any]:
    return {
        "id": "org-001",
        "name": "Acme Corp",
        "type": "organization",
        "org_type": "company",
        "country": "US",
        "aliases": ["Acme"],
        "metadata": {},
    }


@pytest.fixture()
def sample_location_data() -> dict[str, Any]:
    return {
        "id": "loc-001",
        "name": "New York City",
        "type": "location",
        "country": "US",
        "latitude": 40.7128,
        "longitude": -74.0060,
        "region": "New York",
        "metadata": {},
    }


@pytest.fixture()
def sample_asset_data() -> dict[str, Any]:
    return {
        "id": "asset-001",
        "name": "Luxury Yacht Oceania",
        "type": "asset",
        "asset_type": "vessel",
        "value": 5_000_000.0,
        "currency": "USD",
        "owner_id": "person-001",
        "metadata": {},
    }


@pytest.fixture()
def sample_event_create_data() -> dict[str, Any]:
    return {
        "title": "Trade Agreement Signed",
        "summary": "Major trade agreement signed between nations.",
        "category": "economic",
        "occurred_at": "2025-06-15T10:30:00Z",
        "location_name": "Geneva",
        "latitude": 46.2044,
        "longitude": 6.1432,
        "source_url": "https://example.com/news/1",
        "metadata": {"confidence": "high"},
    }


@pytest.fixture()
def sample_event_row() -> MagicMock:
    """Return a MagicMock that looks like an ORM ``Event`` row."""
    row = MagicMock()
    row.id = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    row.title = "Trade Agreement Signed"
    row.summary = "Major trade agreement signed between nations."
    row.category = "economic"
    row.occurred_at = datetime(2025, 6, 15, 10, 30, tzinfo=timezone.utc)
    row.location_name = "Geneva"
    row.latitude = 46.2044
    row.longitude = 6.1432
    row.source_url = "https://example.com/news/1"
    row.created_at = datetime(2025, 6, 15, 12, 0, tzinfo=timezone.utc)
    row.updated_at = datetime(2025, 6, 15, 12, 0, tzinfo=timezone.utc)
    return row


@pytest.fixture()
def sample_watcher_row() -> MagicMock:
    """Return a MagicMock that looks like an ORM ``Watcher`` row."""
    row = MagicMock()
    row.id = uuid.UUID("11111111-2222-3333-4444-555555555555")
    row.entity_id = "person-001"
    row.entity_name = "Jane Doe"
    row.entity_type = "person"
    row.notes = "Key person of interest"
    row.active = True
    row.created_at = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    row.updated_at = datetime(2025, 1, 2, 0, 0, tzinfo=timezone.utc)
    return row


# ---------------------------------------------------------------------------
# Async test client with fully mocked lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _noop_lifespan(app: Any) -> AsyncGenerator[None, None]:
    """A lifespan that does nothing — no external connections are made."""
    yield


@pytest_asyncio.fixture()
async def async_client(
    fake_graph_db: FakeGraphDB,
    fake_search_client: FakeSearchClient,
) -> AsyncGenerator[AsyncClient, None]:
    """Yield an ``httpx.AsyncClient`` wired to the FastAPI app with all services mocked."""
    with (
        patch("app.main.lifespan", _noop_lifespan),
        patch("app.db.neo4j._instance", fake_graph_db),
        patch("app.db.neo4j.get_graph_db", return_value=fake_graph_db),
        patch("app.db.search._instance", fake_search_client),
        patch("app.db.search.get_search_client", return_value=fake_search_client),
        patch("app.routers.entities.get_graph_db", return_value=fake_graph_db),
        patch("app.routers.entities.get_search_client", return_value=fake_search_client),
        patch("app.routers.events.get_search_client", return_value=fake_search_client),
        patch("app.routers.graph.get_graph_db", return_value=fake_graph_db),
        patch("app.routers.search.get_search_client", return_value=fake_search_client),
        patch("app.routers.watchers.get_graph_db", return_value=fake_graph_db),
    ):
        # Re-import to pick up the patched lifespan
        from app.main import app

        # Override the lifespan on the already-created app object
        app.router.lifespan_context = _noop_lifespan

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client
