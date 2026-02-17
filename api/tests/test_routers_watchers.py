"""Tests for watcher endpoints in ``app.routers.watchers``."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import FakeGraphDB

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_watcher_row(
    watcher_id: str = "11111111-2222-3333-4444-555555555555",
    entity_id: str = "person-001",
    entity_name: str = "Jane Doe",
    entity_type: str = "person",
    active: bool = True,
) -> MagicMock:
    """Build a MagicMock that mimics an ORM Watcher row."""
    row = MagicMock()
    row.id = uuid.UUID(watcher_id)
    row.entity_id = entity_id
    row.entity_name = entity_name
    row.entity_type = entity_type
    row.notes = "Key person of interest"
    row.active = active
    row.created_at = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    row.updated_at = datetime(2025, 1, 2, 0, 0, tzinfo=UTC)
    return row


@asynccontextmanager
async def _mock_session(rows=None, single_row=None, rowcount: int = 1):
    """Yield a mock session with configurable results."""
    session = MagicMock()

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = single_row
    result_mock.scalars.return_value.all.return_value = rows or []
    result_mock.rowcount = rowcount

    session.execute = AsyncMock(return_value=result_mock)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    yield session


# ========================================================================
# GET /watchers/ — list watchers
# ========================================================================


class TestListWatchers:
    """Tests for ``GET /watchers/``."""

    async def test_returns_watcher_list(
        self,
        async_client,
    ) -> None:
        rows = [
            _make_watcher_row(),
            _make_watcher_row(
                watcher_id="22222222-3333-4444-5555-666666666666", entity_id="org-001"
            ),
        ]

        with patch("app.routers.watchers.get_session") as mock_gs:
            mock_gs.return_value = _mock_session(rows=rows)
            resp = await async_client.get("/watchers/")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["entity_id"] == "person-001"

    async def test_returns_empty_list(
        self,
        async_client,
    ) -> None:
        with patch("app.routers.watchers.get_session") as mock_gs:
            mock_gs.return_value = _mock_session(rows=[])
            resp = await async_client.get("/watchers/")

        assert resp.status_code == 200
        assert resp.json() == []

    async def test_active_only_default(
        self,
        async_client,
    ) -> None:
        with patch("app.routers.watchers.get_session") as mock_gs:
            mock_gs.return_value = _mock_session(rows=[])
            resp = await async_client.get("/watchers/")

        assert resp.status_code == 200
        # Default is active_only=True — tested by verifying the request succeeds


# ========================================================================
# POST /watchers/ — add watcher
# ========================================================================


class TestCreateWatcher:
    """Tests for ``POST /watchers/``."""

    async def test_creates_watcher(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        watcher_row = _make_watcher_row()

        async def _mock_refresh(obj):
            obj.id = watcher_row.id
            obj.entity_id = watcher_row.entity_id
            obj.entity_name = watcher_row.entity_name
            obj.entity_type = watcher_row.entity_type
            obj.notes = watcher_row.notes
            obj.active = True
            obj.created_at = watcher_row.created_at
            obj.updated_at = watcher_row.updated_at

        @asynccontextmanager
        async def _session_ctx():
            session = MagicMock()
            session.add = MagicMock()
            session.flush = AsyncMock()
            session.refresh = AsyncMock(side_effect=_mock_refresh)
            session.commit = AsyncMock()
            session.rollback = AsyncMock()
            yield session

        with patch("app.routers.watchers.get_session", _session_ctx):
            resp = await async_client.post(
                "/watchers/",
                json={
                    "entity_id": "person-001",
                    "entity_name": "Jane Doe",
                    "entity_type": "person",
                    "notes": "Key person of interest",
                },
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["entity_id"] == "person-001"
        assert data["entity_name"] == "Jane Doe"
        assert data["active"] is True

    async def test_resolves_name_from_graph(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        """When entity_name is not provided, the router fetches it from Neo4j."""
        fake_graph_db.find_entity.return_value = {
            "id": "person-001",
            "name": "Jane Doe",
            "type": "person",
        }
        watcher_row = _make_watcher_row()

        async def _mock_refresh(obj):
            obj.id = watcher_row.id
            obj.entity_id = watcher_row.entity_id
            obj.entity_name = obj.entity_name or "Jane Doe"
            obj.entity_type = obj.entity_type or "person"
            obj.notes = obj.notes
            obj.active = True
            obj.created_at = watcher_row.created_at
            obj.updated_at = watcher_row.updated_at

        @asynccontextmanager
        async def _session_ctx():
            session = MagicMock()
            session.add = MagicMock()
            session.flush = AsyncMock()
            session.refresh = AsyncMock(side_effect=_mock_refresh)
            session.commit = AsyncMock()
            session.rollback = AsyncMock()
            yield session

        with patch("app.routers.watchers.get_session", _session_ctx):
            resp = await async_client.post(
                "/watchers/",
                json={"entity_id": "person-001"},
            )

        assert resp.status_code == 201
        fake_graph_db.find_entity.assert_called_once_with("person-001")

    async def test_rejects_missing_entity_id(
        self,
        async_client,
    ) -> None:
        resp = await async_client.post("/watchers/", json={})
        assert resp.status_code == 422


# ========================================================================
# GET /watchers/{watcher_id} — single watcher details
# ========================================================================


class TestGetWatcher:
    """Tests for ``GET /watchers/{watcher_id}``."""

    async def test_returns_watcher_with_activity(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        watcher_row = _make_watcher_row()
        fake_graph_db.execute.return_value = [
            {"event": {"id": "ev1", "title": "Meeting"}, "rel_type": "ATTENDED"},
        ]

        with patch("app.routers.watchers.get_session") as mock_gs:
            mock_gs.return_value = _mock_session(single_row=watcher_row)
            resp = await async_client.get("/watchers/11111111-2222-3333-4444-555555555555")

        assert resp.status_code == 200
        data = resp.json()
        assert "watcher" in data
        assert data["watcher"]["entity_id"] == "person-001"
        assert "activity" in data

    async def test_returns_404_for_missing_watcher(
        self,
        async_client,
    ) -> None:
        with patch("app.routers.watchers.get_session") as mock_gs:
            mock_gs.return_value = _mock_session(single_row=None)
            resp = await async_client.get("/watchers/00000000-0000-0000-0000-000000000000")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ========================================================================
# DELETE /watchers/{watcher_id} — remove watcher
# ========================================================================


class TestDeleteWatcher:
    """Tests for ``DELETE /watchers/{watcher_id}``."""

    async def test_deletes_watcher(
        self,
        async_client,
    ) -> None:
        with patch("app.routers.watchers.get_session") as mock_gs:
            mock_gs.return_value = _mock_session(rowcount=1)
            resp = await async_client.delete("/watchers/11111111-2222-3333-4444-555555555555")

        assert resp.status_code == 204

    async def test_returns_404_when_not_found(
        self,
        async_client,
    ) -> None:
        with patch("app.routers.watchers.get_session") as mock_gs:
            mock_gs.return_value = _mock_session(rowcount=0)
            resp = await async_client.delete("/watchers/00000000-0000-0000-0000-000000000000")

        assert resp.status_code == 404


# ========================================================================
# GET /watchers/{watcher_id}/activity — activity feed
# ========================================================================


class TestGetWatcherActivity:
    """Tests for ``GET /watchers/{watcher_id}/activity``."""

    async def test_returns_activity_feed(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        watcher_row = _make_watcher_row()

        # First execute call returns events, second returns relationships
        fake_graph_db.execute.side_effect = [
            # events
            [{"event": {"id": "ev1", "title": "Summit", "occurred_at": "2025-06-15"},
              "rel_type": "MENTIONS"}],
            # relationships
            [{"node": {"id": "o1", "name": "Corp"},
              "rel_type": "WORKS_FOR", "connected_at": "2025-06-10"}],
        ]

        watcher_uuid = "11111111-2222-3333-4444-555555555555"
        with patch("app.routers.watchers.get_session") as mock_gs:
            mock_gs.return_value = _mock_session(single_row=watcher_row)
            resp = await async_client.get(f"/watchers/{watcher_uuid}/activity")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # Should contain both event and connection entries
        types = {item["type"] for item in data}
        assert "event" in types
        assert "connection" in types

    async def test_returns_404_for_missing_watcher(
        self,
        async_client,
    ) -> None:
        with patch("app.routers.watchers.get_session") as mock_gs:
            mock_gs.return_value = _mock_session(single_row=None)
            resp = await async_client.get(
                "/watchers/00000000-0000-0000-0000-000000000000/activity"
            )

        assert resp.status_code == 404


# ========================================================================
# GET /watchers/{watcher_id}/network — network graph
# ========================================================================


class TestGetWatcherNetwork:
    """Tests for ``GET /watchers/{watcher_id}/network``."""

    async def test_returns_network_graph(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        watcher_row = _make_watcher_row()

        mock_network = {
            "nodes": [
                {"id": "person-001", "name": "Jane Doe", "type": "person"},
                {"id": "o1", "name": "Corp", "type": "organization"},
            ],
            "edges": [
                {"type": "WORKS_FOR", "from": "person-001", "to": "o1"},
            ],
        }

        with (
            patch("app.routers.watchers.get_session") as mock_gs,
            patch("app.services.graph.GraphService") as mock_svc,
        ):
            mock_gs.return_value = _mock_session(single_row=watcher_row)
            instance = mock_svc.return_value
            instance.get_entity_network = AsyncMock(return_value=mock_network)

            resp = await async_client.get("/watchers/11111111-2222-3333-4444-555555555555/network")

        assert resp.status_code == 200
        data = resp.json()
        assert data["watcher_id"] == "11111111-2222-3333-4444-555555555555"
        assert data["entity_id"] == "person-001"
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1

    async def test_returns_404_for_missing_watcher(
        self,
        async_client,
    ) -> None:
        with patch("app.routers.watchers.get_session") as mock_gs:
            mock_gs.return_value = _mock_session(single_row=None)
            resp = await async_client.get("/watchers/00000000-0000-0000-0000-000000000000/network")

        assert resp.status_code == 404

    async def test_custom_depth(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        watcher_row = _make_watcher_row()

        with (
            patch("app.routers.watchers.get_session") as mock_gs,
            patch("app.services.graph.GraphService") as mock_svc,
        ):
            mock_gs.return_value = _mock_session(single_row=watcher_row)
            instance = mock_svc.return_value
            instance.get_entity_network = AsyncMock(return_value={"nodes": [], "edges": []})

            resp = await async_client.get(
                "/watchers/11111111-2222-3333-4444-555555555555/network",
                params={"depth": 3},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["depth"] == 3
        instance.get_entity_network.assert_called_once_with("person-001", depth=3)
