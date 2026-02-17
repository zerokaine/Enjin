"""Tests for graph analytical endpoints in ``app.routers.graph``."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import FakeGraphDB


pytestmark = pytest.mark.asyncio


# ========================================================================
# GET /graph/connections — shortest path
# ========================================================================


class TestGetConnections:
    """Tests for ``GET /graph/connections``."""

    async def test_returns_path_between_entities(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        # Patch GraphService.find_shortest_path to return a path
        mock_path = {
            "from_id": "p1",
            "to_id": "o1",
            "hops": 2,
            "nodes": [
                {"id": "p1", "name": "Alice", "type": "person"},
                {"id": "middle", "name": "Bridge", "type": "organization"},
                {"id": "o1", "name": "Corp", "type": "organization"},
            ],
            "edges": [
                {"type": "WORKS_FOR", "from": "p1", "to": "middle", "props": {}},
                {"type": "PARTNER_OF", "from": "middle", "to": "o1", "props": {}},
            ],
        }

        with patch("app.routers.graph.GraphService") as MockSvc:
            instance = MockSvc.return_value
            instance.find_shortest_path = AsyncMock(return_value=mock_path)

            resp = await async_client.get(
                "/graph/connections",
                params={"from_id": "p1", "to_id": "o1"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["from_id"] == "p1"
        assert data["to_id"] == "o1"
        assert data["hops"] == 2
        assert len(data["nodes"]) == 3
        assert len(data["edges"]) == 2

    async def test_returns_404_when_no_path(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        with patch("app.routers.graph.GraphService") as MockSvc:
            instance = MockSvc.return_value
            instance.find_shortest_path = AsyncMock(return_value=None)

            resp = await async_client.get(
                "/graph/connections",
                params={"from_id": "p1", "to_id": "p2"},
            )

        assert resp.status_code == 404
        assert "no path" in resp.json()["detail"].lower()

    async def test_custom_max_depth(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        with patch("app.routers.graph.GraphService") as MockSvc:
            instance = MockSvc.return_value
            instance.find_shortest_path = AsyncMock(return_value=None)

            resp = await async_client.get(
                "/graph/connections",
                params={"from_id": "p1", "to_id": "p2", "max_depth": 3},
            )

        assert resp.status_code == 404
        instance.find_shortest_path.assert_called_once_with("p1", "p2", max_depth=3)

    async def test_missing_required_params(
        self,
        async_client,
    ) -> None:
        resp = await async_client.get("/graph/connections")
        assert resp.status_code == 422  # Missing from_id and to_id


# ========================================================================
# GET /graph/ripple/{event_id} — ripple trace
# ========================================================================


class TestGetRipple:
    """Tests for ``GET /graph/ripple/{event_id}``."""

    async def test_returns_ripple_trace(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        mock_ripple = {
            "origin": {"id": "ev1", "title": "Big Event", "_labels": ["Event"]},
            "max_hops": 3,
            "rings": [
                [{"id": "p1", "name": "Alice"}],
                [{"id": "o1", "name": "Corp"}],
                [],
            ],
            "edges": [
                {"type": "MENTIONS", "from": "ev1", "to": "p1"},
                {"type": "WORKS_FOR", "from": "p1", "to": "o1"},
            ],
            "total_nodes": 2,
        }

        with patch("app.routers.graph.GraphService") as MockSvc:
            instance = MockSvc.return_value
            instance.get_ripple_trace = AsyncMock(return_value=mock_ripple)

            resp = await async_client.get("/graph/ripple/ev1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["origin"]["id"] == "ev1"
        assert len(data["rings"]) == 3
        assert data["total_nodes"] == 2

    async def test_returns_404_when_event_not_in_graph(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        with patch("app.routers.graph.GraphService") as MockSvc:
            instance = MockSvc.return_value
            instance.get_ripple_trace = AsyncMock(return_value=None)

            resp = await async_client.get("/graph/ripple/nonexistent")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    async def test_custom_max_hops(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        with patch("app.routers.graph.GraphService") as MockSvc:
            instance = MockSvc.return_value
            instance.get_ripple_trace = AsyncMock(return_value=None)

            resp = await async_client.get(
                "/graph/ripple/ev1",
                params={"max_hops": 5},
            )

        instance.get_ripple_trace.assert_called_once_with("ev1", max_hops=5)


# ========================================================================
# GET /graph/cluster/{location} — geographic cluster
# ========================================================================


class TestGetCluster:
    """Tests for ``GET /graph/cluster/{location}``."""

    async def test_returns_cluster(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        mock_cluster = {
            "entities": [
                {"id": "loc1", "name": "Office", "distance_km": 5.2},
            ],
            "events": [
                {"id": "ev1", "title": "Protest", "distance_km": 12.3},
            ],
            "total_entities": 1,
            "total_events": 1,
        }

        with patch("app.routers.graph.GraphService") as MockSvc:
            instance = MockSvc.return_value
            instance.get_area_cluster = AsyncMock(return_value=mock_cluster)

            resp = await async_client.get(
                "/graph/cluster/Geneva",
                params={"lat": 46.2044, "lon": 6.1432},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["location"] == "Geneva"
        assert data["center"]["latitude"] == pytest.approx(46.2044)
        assert data["center"]["longitude"] == pytest.approx(6.1432)
        assert data["radius_km"] == 50  # default
        assert len(data["entities"]) == 1
        assert len(data["events"]) == 1

    async def test_custom_radius(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        with patch("app.routers.graph.GraphService") as MockSvc:
            instance = MockSvc.return_value
            instance.get_area_cluster = AsyncMock(
                return_value={"entities": [], "events": [], "total_entities": 0, "total_events": 0}
            )

            resp = await async_client.get(
                "/graph/cluster/Berlin",
                params={"lat": 52.52, "lon": 13.405, "radius_km": 100},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["radius_km"] == 100
        instance.get_area_cluster.assert_called_once_with(52.52, 13.405, 100)

    async def test_missing_lat_lon(
        self,
        async_client,
    ) -> None:
        resp = await async_client.get("/graph/cluster/TestCity")
        assert resp.status_code == 422  # lat and lon are required

    @pytest.mark.parametrize(
        "lat,lon",
        [(-91, 0), (91, 0), (0, -181), (0, 181)],
        ids=["lat-too-low", "lat-too-high", "lon-too-low", "lon-too-high"],
    )
    async def test_invalid_coordinates(
        self,
        async_client,
        lat: float,
        lon: float,
    ) -> None:
        resp = await async_client.get(
            "/graph/cluster/Bad",
            params={"lat": lat, "lon": lon},
        )
        assert resp.status_code == 422
