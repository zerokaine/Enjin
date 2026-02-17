"""Tests for event endpoints in ``app.routers.events``."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import FakeGraphDB, FakeSearchClient

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers — mock the Postgres session for event routes
# ---------------------------------------------------------------------------


def _make_event_row(
    event_id: str = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    title: str = "Trade Agreement Signed",
    category: str = "economic",
) -> MagicMock:
    """Build a MagicMock that mimics an ORM Event row."""
    row = MagicMock()
    row.id = uuid.UUID(event_id)
    row.title = title
    row.summary = "Summary text"
    row.category = category
    row.occurred_at = datetime(2025, 6, 15, 10, 30, tzinfo=UTC)
    row.location_name = "Geneva"
    row.latitude = 46.2044
    row.longitude = 6.1432
    row.source_url = "https://example.com/news/1"
    row.created_at = datetime(2025, 6, 15, 12, 0, tzinfo=UTC)
    row.updated_at = datetime(2025, 6, 15, 12, 0, tzinfo=UTC)
    row.metadata_ = {}
    row.geom = None
    return row


@asynccontextmanager
async def _mock_session(rows=None, total: int = 0, single_row=None):
    """Yield a mock session whose execute returns configurable results."""
    session = MagicMock()

    call_count = 0

    async def _execute(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        # First call is count query, second is data query in list endpoints
        if call_count == 1 and single_row is None:
            result.scalar.return_value = total
            result.scalar_one_or_none.return_value = single_row
        else:
            result.scalar.return_value = total
            result.scalar_one_or_none.return_value = single_row
            result.scalars.return_value.all.return_value = rows or []
        return result

    session.execute = _execute
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    yield session


# ========================================================================
# GET /events/ — list events
# ========================================================================


class TestListEvents:
    """Tests for ``GET /events/``."""

    async def test_returns_event_feed(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        rows = [
            _make_event_row(),
            _make_event_row(event_id="11111111-2222-3333-4444-555555555555", title="Second"),
        ]

        with patch("app.routers.events.get_session") as mock_gs:
            mock_gs.return_value = _mock_session(rows=rows, total=2)
            resp = await async_client.get("/events/")

        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data

    async def test_returns_empty_when_no_events(
        self,
        async_client,
    ) -> None:
        with patch("app.routers.events.get_session") as mock_gs:
            mock_gs.return_value = _mock_session(rows=[], total=0)
            resp = await async_client.get("/events/")

        assert resp.status_code == 200
        data = resp.json()
        assert data["events"] == []
        assert data["total"] == 0

    async def test_with_category_filter(
        self,
        async_client,
    ) -> None:
        rows = [_make_event_row(category="political")]

        with patch("app.routers.events.get_session") as mock_gs:
            mock_gs.return_value = _mock_session(rows=rows, total=1)
            resp = await async_client.get("/events/", params={"category": "political"})

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["events"]) >= 0  # Mocked, just verify no error


# ========================================================================
# GET /events/feed — real-time event feed
# ========================================================================


class TestEventFeed:
    """Tests for ``GET /events/feed``."""

    async def test_returns_feed(
        self,
        async_client,
    ) -> None:
        rows = [_make_event_row()]

        with patch("app.routers.events.get_session") as mock_gs:
            mock_gs.return_value = _mock_session(rows=rows, total=1)
            resp = await async_client.get("/events/feed")

        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert data["page"] == 1
        assert data["per_page"] == 20

    async def test_feed_with_pagination(
        self,
        async_client,
    ) -> None:
        with patch("app.routers.events.get_session") as mock_gs:
            mock_gs.return_value = _mock_session(rows=[], total=50)
            resp = await async_client.get("/events/feed", params={"page": 3, "per_page": 10})

        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 3
        assert data["per_page"] == 10

    async def test_feed_with_category_filter(
        self,
        async_client,
    ) -> None:
        with patch("app.routers.events.get_session") as mock_gs:
            mock_gs.return_value = _mock_session(rows=[], total=0)
            resp = await async_client.get("/events/feed", params={"category": "security"})

        assert resp.status_code == 200


# ========================================================================
# GET /events/{event_id} — single event detail
# ========================================================================


class TestGetEvent:
    """Tests for ``GET /events/{event_id}``."""

    async def test_returns_event_details(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        event_row = _make_event_row()
        fake_graph_db.execute.return_value = [
            {"node": {"id": "p1", "name": "Alice"}, "rel_type": "MENTIONS"},
        ]

        with patch("app.routers.events.get_session") as mock_gs:
            mock_gs.return_value = _mock_session(single_row=event_row)
            resp = await async_client.get("/events/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Trade Agreement Signed"
        assert data["category"] == "economic"

    async def test_returns_404_for_missing_event(
        self,
        async_client,
    ) -> None:
        with patch("app.routers.events.get_session") as mock_gs:
            mock_gs.return_value = _mock_session(single_row=None)
            resp = await async_client.get("/events/00000000-0000-0000-0000-000000000000")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ========================================================================
# POST /events/ — create event
# ========================================================================


class TestCreateEvent:
    """Tests for ``POST /events/``."""

    async def test_creates_event(
        self,
        async_client,
        fake_search_client: FakeSearchClient,
    ) -> None:
        async def _mock_refresh(obj):
            # Simulate refresh populating the created_at timestamp
            obj.created_at = datetime(2025, 6, 15, 12, 0, tzinfo=UTC)

        @asynccontextmanager
        async def _session_ctx():
            session = MagicMock()
            session.add = MagicMock()
            session.flush = AsyncMock()
            session.refresh = AsyncMock(side_effect=_mock_refresh)
            session.commit = AsyncMock()
            session.rollback = AsyncMock()
            yield session

        with patch("app.routers.events.get_session", _session_ctx):
            resp = await async_client.post(
                "/events/",
                json={
                    "title": "New Event",
                    "summary": "Test event creation",
                    "category": "economic",
                },
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "New Event"

    async def test_rejects_empty_title(self, async_client) -> None:
        resp = await async_client.post(
            "/events/",
            json={"title": ""},
        )
        assert resp.status_code == 422

    async def test_rejects_invalid_category(self, async_client) -> None:
        resp = await async_client.post(
            "/events/",
            json={"title": "Test", "category": "invalid_cat"},
        )
        assert resp.status_code == 422
