"""Tests for ``app.services.graph.GraphService`` with a mocked Neo4j backend."""

from __future__ import annotations

import pytest

from app.services.graph import GraphService
from tests.conftest import FakeGraphDB

pytestmark = pytest.mark.asyncio


# ========================================================================
# find_shortest_path
# ========================================================================


class TestFindShortestPath:
    """Tests for ``GraphService.find_shortest_path``."""

    async def test_returns_path(self, fake_graph_db: FakeGraphDB) -> None:
        fake_graph_db.execute.return_value = [
            {
                "nodes": [
                    {"id": "p1", "name": "Alice", "_labels": ["Person"]},
                    {"id": "o1", "name": "Corp", "_labels": ["Organization"]},
                ],
                "edges": [
                    {"type": "WORKS_FOR", "from": "p1", "to": "o1", "props": {}},
                ],
                "hops": 1,
            }
        ]

        svc = GraphService(fake_graph_db)
        result = await svc.find_shortest_path("p1", "o1")

        assert result is not None
        assert result["from_id"] == "p1"
        assert result["to_id"] == "o1"
        assert result["hops"] == 1
        assert len(result["nodes"]) == 2
        assert len(result["edges"]) == 1

    async def test_returns_none_when_no_path(self, fake_graph_db: FakeGraphDB) -> None:
        fake_graph_db.execute.return_value = []

        svc = GraphService(fake_graph_db)
        result = await svc.find_shortest_path("p1", "p2")

        assert result is None

    async def test_respects_max_depth(self, fake_graph_db: FakeGraphDB) -> None:
        fake_graph_db.execute.return_value = []

        svc = GraphService(fake_graph_db)
        await svc.find_shortest_path("p1", "p2", max_depth=3)

        # Verify the query string includes the max_depth
        call_args = fake_graph_db.execute.call_args
        query = call_args[0][0]
        assert "3" in query

    async def test_multi_hop_path(self, fake_graph_db: FakeGraphDB) -> None:
        fake_graph_db.execute.return_value = [
            {
                "nodes": [
                    {"id": "a", "name": "A"},
                    {"id": "b", "name": "B"},
                    {"id": "c", "name": "C"},
                ],
                "edges": [
                    {"type": "KNOWS", "from": "a", "to": "b", "props": {}},
                    {"type": "KNOWS", "from": "b", "to": "c", "props": {}},
                ],
                "hops": 2,
            }
        ]

        svc = GraphService(fake_graph_db)
        result = await svc.find_shortest_path("a", "c")

        assert result is not None
        assert result["hops"] == 2
        assert len(result["nodes"]) == 3
        assert len(result["edges"]) == 2


# ========================================================================
# get_entity_network
# ========================================================================


class TestGetEntityNetwork:
    """Tests for ``GraphService.get_entity_network``."""

    async def test_returns_network_with_nodes_and_edges(
        self, fake_graph_db: FakeGraphDB
    ) -> None:
        fake_graph_db.execute.return_value = [
            {
                "nodes": [
                    {"id": "p1", "name": "Alice", "_labels": ["Person"]},
                    {"id": "o1", "name": "Corp", "_labels": ["Organization"]},
                    {"id": "o2", "name": "NGO", "_labels": ["Organization"]},
                ],
                "edges": [
                    {"type": "WORKS_FOR", "from": "p1", "to": "o1", "props": {}},
                    {"type": "DONATES_TO", "from": "p1", "to": "o2", "props": {}},
                ],
            }
        ]

        svc = GraphService(fake_graph_db)
        result = await svc.get_entity_network("p1", depth=2)

        assert len(result["nodes"]) == 3
        assert len(result["edges"]) == 2

    async def test_returns_single_node_when_no_connections(
        self, fake_graph_db: FakeGraphDB
    ) -> None:
        # First call (network query) returns empty
        # Second call (find_entity) returns the lone entity
        fake_graph_db.execute.return_value = []
        fake_graph_db.find_entity.return_value = {
            "id": "p1",
            "name": "Lonely",
            "_labels": ["Person"],
        }

        svc = GraphService(fake_graph_db)
        result = await svc.get_entity_network("p1")

        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["id"] == "p1"
        assert result["edges"] == []

    async def test_returns_empty_when_entity_not_found(
        self, fake_graph_db: FakeGraphDB
    ) -> None:
        fake_graph_db.execute.return_value = []
        fake_graph_db.find_entity.return_value = None

        svc = GraphService(fake_graph_db)
        result = await svc.get_entity_network("nonexistent")

        assert result["nodes"] == []
        assert result["edges"] == []

    async def test_respects_depth_parameter(
        self, fake_graph_db: FakeGraphDB
    ) -> None:
        fake_graph_db.execute.return_value = []
        fake_graph_db.find_entity.return_value = None

        svc = GraphService(fake_graph_db)
        await svc.get_entity_network("p1", depth=4)

        query = fake_graph_db.execute.call_args[0][0]
        assert "4" in query


# ========================================================================
# get_ripple_trace
# ========================================================================


class TestGetRippleTrace:
    """Tests for ``GraphService.get_ripple_trace``."""

    async def test_returns_ripple_with_rings(
        self, fake_graph_db: FakeGraphDB
    ) -> None:
        # First call: check event exists
        # Then one call per hop
        fake_graph_db.execute.side_effect = [
            # Event exists
            [{"event": {"id": "ev1", "title": "Big Event", "_labels": ["Event"]}}],
            # Hop 1
            [
                {
                    "node": {"id": "p1", "name": "Alice", "_labels": ["Person"]},
                    "rels": [{"type": "MENTIONS", "from": "ev1", "to": "p1"}],
                }
            ],
            # Hop 2
            [
                {
                    "node": {"id": "o1", "name": "Corp", "_labels": ["Organization"]},
                    "rels": [{"type": "WORKS_FOR", "from": "p1", "to": "o1"}],
                }
            ],
            # Hop 3
            [],
        ]

        svc = GraphService(fake_graph_db)
        result = await svc.get_ripple_trace("ev1", max_hops=3)

        assert result is not None
        assert result["origin"]["id"] == "ev1"
        assert result["max_hops"] == 3
        assert len(result["rings"]) == 3
        assert len(result["rings"][0]) == 1  # hop 1: Alice
        assert len(result["rings"][1]) == 1  # hop 2: Corp
        assert len(result["rings"][2]) == 0  # hop 3: empty
        assert result["total_nodes"] == 2
        assert len(result["edges"]) == 2

    async def test_returns_none_when_event_not_found(
        self, fake_graph_db: FakeGraphDB
    ) -> None:
        fake_graph_db.execute.return_value = []

        svc = GraphService(fake_graph_db)
        result = await svc.get_ripple_trace("nonexistent")

        assert result is None

    async def test_deduplicates_edges(
        self, fake_graph_db: FakeGraphDB
    ) -> None:
        fake_graph_db.execute.side_effect = [
            # Event exists
            [{"event": {"id": "ev1", "title": "Event", "_labels": ["Event"]}}],
            # Hop 1 — two nodes sharing the same edge
            [
                {
                    "node": {"id": "p1", "name": "Alice"},
                    "rels": [{"type": "MENTIONS", "from": "ev1", "to": "p1"}],
                },
                {
                    "node": {"id": "p2", "name": "Bob"},
                    "rels": [{"type": "MENTIONS", "from": "ev1", "to": "p1"}],  # duplicate
                },
            ],
        ]

        svc = GraphService(fake_graph_db)
        result = await svc.get_ripple_trace("ev1", max_hops=1)

        assert result is not None
        # The duplicate edge should have been removed
        assert len(result["edges"]) == 1

    async def test_empty_rings_when_no_connections(
        self, fake_graph_db: FakeGraphDB
    ) -> None:
        fake_graph_db.execute.side_effect = [
            # Event exists
            [{"event": {"id": "ev1", "title": "Isolated Event", "_labels": ["Event"]}}],
            # Hop 1: empty
            [],
            # Hop 2: empty
            [],
        ]

        svc = GraphService(fake_graph_db)
        result = await svc.get_ripple_trace("ev1", max_hops=2)

        assert result is not None
        assert all(len(ring) == 0 for ring in result["rings"])
        assert result["total_nodes"] == 0
        assert result["edges"] == []


# ========================================================================
# get_area_cluster
# ========================================================================


class TestGetAreaCluster:
    """Tests for ``GraphService.get_area_cluster``."""

    async def test_returns_entities_and_events(
        self, fake_graph_db: FakeGraphDB
    ) -> None:
        fake_graph_db.execute.return_value = [
            {
                "node": {
                    "id": "loc1", "name": "Office",
                    "_labels": ["Location"], "latitude": 46.2, "longitude": 6.1,
                },
                "dist_km": 5.2,
            },
            {
                "node": {
                    "id": "ev1", "title": "Protest",
                    "_labels": ["Event"], "latitude": 46.3, "longitude": 6.2,
                },
                "dist_km": 12.3,
            },
        ]

        svc = GraphService(fake_graph_db)
        result = await svc.get_area_cluster(46.2044, 6.1432, radius_km=50)

        assert result["total_entities"] == 1
        assert result["total_events"] == 1
        assert result["entities"][0]["id"] == "loc1"
        assert result["entities"][0]["distance_km"] == 5.2
        assert result["events"][0]["id"] == "ev1"
        assert result["events"][0]["distance_km"] == 12.3

    async def test_returns_empty_when_nothing_nearby(
        self, fake_graph_db: FakeGraphDB
    ) -> None:
        fake_graph_db.execute.return_value = []

        svc = GraphService(fake_graph_db)
        result = await svc.get_area_cluster(0, 0, radius_km=10)

        assert result["entities"] == []
        assert result["events"] == []
        assert result["total_entities"] == 0
        assert result["total_events"] == 0

    async def test_passes_radius_to_query(
        self, fake_graph_db: FakeGraphDB
    ) -> None:
        fake_graph_db.execute.return_value = []

        svc = GraphService(fake_graph_db)
        await svc.get_area_cluster(52.52, 13.405, radius_km=100)

        call_args = fake_graph_db.execute.call_args
        params = call_args[0][1]
        assert params["lat"] == pytest.approx(52.52)
        assert params["lon"] == pytest.approx(13.405)
        assert params["radius"] == 100

    @pytest.mark.parametrize(
        "lat,lon",
        [(0, 0), (90, 180), (-90, -180), (46.2, 6.14)],
        ids=["origin", "ne-extreme", "sw-extreme", "geneva"],
    )
    async def test_various_coordinates(
        self,
        fake_graph_db: FakeGraphDB,
        lat: float,
        lon: float,
    ) -> None:
        fake_graph_db.execute.return_value = []

        svc = GraphService(fake_graph_db)
        result = await svc.get_area_cluster(lat, lon)

        assert isinstance(result, dict)
        assert "entities" in result
        assert "events" in result

    async def test_distance_rounding(
        self, fake_graph_db: FakeGraphDB
    ) -> None:
        fake_graph_db.execute.return_value = [
            {
                "node": {"id": "loc1", "name": "Place", "_labels": ["Location"]},
                "dist_km": 3.14159265,
            },
        ]

        svc = GraphService(fake_graph_db)
        result = await svc.get_area_cluster(46.2, 6.1)

        assert result["entities"][0]["distance_km"] == 3.14  # rounded to 2 decimals
