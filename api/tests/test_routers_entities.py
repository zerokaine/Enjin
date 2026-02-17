"""Tests for entity endpoints in ``app.routers.entities``."""

from __future__ import annotations

import pytest

from tests.conftest import FakeGraphDB, FakeSearchClient

pytestmark = pytest.mark.asyncio


# ========================================================================
# GET /entities/ — list entities
# ========================================================================


class TestListEntities:
    """Tests for ``GET /entities/``."""

    async def test_returns_empty_list_when_no_entities(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        fake_graph_db.execute.return_value = []
        resp = await async_client.get("/entities/")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_entity_list(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        fake_graph_db.execute.return_value = [
            {"entity": {"id": "p1", "name": "Alice", "type": "person"}},
            {"entity": {"id": "o1", "name": "Corp", "type": "organization"}},
        ]
        resp = await async_client.get("/entities/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["id"] == "p1"
        assert data[1]["id"] == "o1"

    async def test_with_type_filter(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        fake_graph_db.execute.return_value = [
            {"entity": {"id": "p1", "name": "Alice", "type": "person"}},
        ]
        resp = await async_client.get("/entities/", params={"type": "person"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["type"] == "person"
        # Verify the execute call used a label-filtered query
        call_args = fake_graph_db.execute.call_args
        query = call_args[0][0]
        assert "Person" in query

    async def test_with_text_search(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        fake_graph_db.search_entities.return_value = [
            {"entity": {"id": "p1", "name": "Alice Smith", "type": "person"}, "score": 0.9},
        ]
        resp = await async_client.get("/entities/", params={"q": "Alice"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Alice Smith"
        fake_graph_db.search_entities.assert_called_once()

    async def test_pagination_params(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        fake_graph_db.execute.return_value = []
        resp = await async_client.get("/entities/", params={"page": 2, "per_page": 10})
        assert resp.status_code == 200
        # Verify skip/limit were passed
        call_args = fake_graph_db.execute.call_args
        params = call_args[0][1]
        assert params["skip"] == 10  # (page-1) * per_page
        assert params["limit"] == 10


# ========================================================================
# GET /entities/{entity_id} — single entity
# ========================================================================


class TestGetEntity:
    """Tests for ``GET /entities/{entity_id}``."""

    async def test_returns_entity_with_relationships(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        fake_graph_db.find_entity.return_value = {
            "id": "p1",
            "name": "Alice",
            "type": "person",
            "metadata": {},
        }
        fake_graph_db.find_connections.return_value = [
            {
                "node": {"id": "o1", "name": "Corp", "type": "organization"},
                "rels": [{"type": "WORKS_FOR", "props": {}}],
            },
        ]
        # Events query
        fake_graph_db.execute.return_value = [
            {
                "event": {"id": "ev1", "title": "Meeting"},
                "rel_type": "ATTENDED",
            },
        ]

        resp = await async_client.get("/entities/p1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entity"]["id"] == "p1"
        assert len(data["relationships"]) == 1
        assert data["relationships"][0]["target"]["id"] == "o1"
        assert len(data["events"]) == 1
        assert data["events"][0]["relationship"] == "ATTENDED"

    async def test_returns_404_for_missing_entity(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        fake_graph_db.find_entity.return_value = None
        resp = await async_client.get("/entities/nonexistent")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ========================================================================
# GET /entities/{entity_id}/connections — connection graph
# ========================================================================


class TestGetEntityConnections:
    """Tests for ``GET /entities/{entity_id}/connections``."""

    async def test_returns_graph_data(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        fake_graph_db.find_entity.return_value = {
            "id": "p1",
            "name": "Alice",
            "type": "person",
        }
        fake_graph_db.find_connections.return_value = [
            {
                "node": {"id": "o1", "name": "Corp", "type": "organization"},
                "rels": [{"type": "WORKS_FOR", "props": {}}],
            },
        ]

        resp = await async_client.get("/entities/p1/connections")
        assert resp.status_code == 200
        data = resp.json()
        assert data["center"] == "p1"
        assert data["depth"] == 1
        assert len(data["nodes"]) == 2  # p1 + o1
        assert len(data["edges"]) == 1

    async def test_returns_404_for_missing_entity(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        fake_graph_db.find_entity.return_value = None
        resp = await async_client.get("/entities/nonexistent/connections")
        assert resp.status_code == 404

    async def test_custom_depth(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        fake_graph_db.find_entity.return_value = {
            "id": "p1",
            "name": "Alice",
            "type": "person",
        }
        fake_graph_db.find_connections.return_value = []

        resp = await async_client.get("/entities/p1/connections", params={"depth": 3})
        assert resp.status_code == 200
        data = resp.json()
        assert data["depth"] == 3
        # Verify find_connections was called with depth=3
        fake_graph_db.find_connections.assert_called_once_with("p1", depth=3)


# ========================================================================
# POST /entities/ — create entity
# ========================================================================


class TestCreateEntity:
    """Tests for ``POST /entities/``."""

    async def test_creates_entity(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        fake_graph_db.create_entity.return_value = {
            "id": "new-id",
            "name": "New Person",
            "type": "person",
        }

        resp = await async_client.post(
            "/entities/",
            json={"id": "new-id", "name": "New Person", "type": "person"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "New Person"
        fake_graph_db.create_entity.assert_called_once()

    async def test_generates_uuid_when_id_missing(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
    ) -> None:
        fake_graph_db.create_entity.return_value = {
            "id": "generated-uuid",
            "name": "Auto ID",
            "type": "person",
        }

        resp = await async_client.post(
            "/entities/",
            json={"id": "", "name": "Auto ID", "type": "person"},
        )
        assert resp.status_code == 201
        # Verify create_entity was called with a non-empty ID
        call_args = fake_graph_db.create_entity.call_args[0]
        props = call_args[1]
        assert props.get("id", "") != ""

    async def test_indexes_in_search(
        self,
        async_client,
        fake_graph_db: FakeGraphDB,
        fake_search_client: FakeSearchClient,
    ) -> None:
        fake_graph_db.create_entity.return_value = {
            "id": "s1",
            "name": "Searchable",
            "type": "person",
        }

        await async_client.post(
            "/entities/",
            json={"id": "s1", "name": "Searchable", "type": "person"},
        )
        fake_search_client.index_entity.assert_called_once()

    async def test_rejects_missing_name(self, async_client) -> None:
        resp = await async_client.post(
            "/entities/",
            json={"id": "x", "type": "person"},
        )
        assert resp.status_code == 422
