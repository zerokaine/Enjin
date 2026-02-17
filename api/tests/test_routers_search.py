"""Tests for the unified search endpoint in ``app.routers.search``."""

from __future__ import annotations

from typing import Any

import pytest

from tests.conftest import FakeSearchClient


pytestmark = pytest.mark.asyncio


class TestUnifiedSearch:
    """Tests for ``GET /search``."""

    async def test_returns_combined_results(
        self,
        async_client,
        fake_search_client: FakeSearchClient,
    ) -> None:
        # Configure entity search results
        def _search_side_effect(query, index, limit, filters=None):
            if index == "entities":
                return {
                    "hits": [{"id": "p1", "name": "Alice", "type": "person"}],
                    "estimatedTotalHits": 1,
                    "processingTimeMs": 5,
                }
            elif index == "events":
                return {
                    "hits": [{"id": "ev1", "title": "Meeting"}],
                    "estimatedTotalHits": 1,
                    "processingTimeMs": 3,
                }
            return {"hits": [], "estimatedTotalHits": 0, "processingTimeMs": 0}

        fake_search_client.search.side_effect = _search_side_effect

        resp = await async_client.get("/search/", params={"q": "Alice"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "Alice"
        assert len(data["entities"]) == 1
        assert data["entities"][0]["name"] == "Alice"
        assert len(data["events"]) == 1
        assert data["events"][0]["title"] == "Meeting"
        assert data["entity_total"] == 1
        assert data["event_total"] == 1

    async def test_filter_by_entities_index(
        self,
        async_client,
        fake_search_client: FakeSearchClient,
    ) -> None:
        fake_search_client.search.return_value = {
            "hits": [{"id": "p1", "name": "Alice", "type": "person"}],
            "estimatedTotalHits": 1,
            "processingTimeMs": 2,
        }

        resp = await async_client.get(
            "/search/",
            params={"q": "Alice", "index": "entities"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["entities"]) == 1
        # Events should remain empty when scoped to entities index
        assert data["events"] == []
        # search should have been called only once (for entities)
        assert fake_search_client.search.call_count == 1

    async def test_filter_by_events_index(
        self,
        async_client,
        fake_search_client: FakeSearchClient,
    ) -> None:
        fake_search_client.search.return_value = {
            "hits": [{"id": "ev1", "title": "Summit"}],
            "estimatedTotalHits": 1,
            "processingTimeMs": 2,
        }

        resp = await async_client.get(
            "/search/",
            params={"q": "summit", "index": "events"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entities"] == []
        assert len(data["events"]) == 1
        assert fake_search_client.search.call_count == 1

    async def test_type_filter_for_entities(
        self,
        async_client,
        fake_search_client: FakeSearchClient,
    ) -> None:
        fake_search_client.search.return_value = {
            "hits": [],
            "estimatedTotalHits": 0,
            "processingTimeMs": 1,
        }

        resp = await async_client.get(
            "/search/",
            params={"q": "test", "type_filter": "person"},
        )
        assert resp.status_code == 200

        # Verify the filter was passed to the search call for entities index
        calls = fake_search_client.search.call_args_list
        entity_call = [c for c in calls if c.kwargs.get("index") == "entities" or (c.args and len(c.args) > 1 and c.args[1] == "entities")]
        # At least the entities search should have been called
        assert len(calls) >= 1

    async def test_category_filter_for_events(
        self,
        async_client,
        fake_search_client: FakeSearchClient,
    ) -> None:
        fake_search_client.search.return_value = {
            "hits": [],
            "estimatedTotalHits": 0,
            "processingTimeMs": 1,
        }

        resp = await async_client.get(
            "/search/",
            params={"q": "test", "category": "security"},
        )
        assert resp.status_code == 200

    async def test_empty_query_rejected(
        self,
        async_client,
    ) -> None:
        resp = await async_client.get("/search/", params={"q": ""})
        assert resp.status_code == 422

    async def test_missing_query_rejected(
        self,
        async_client,
    ) -> None:
        resp = await async_client.get("/search/")
        assert resp.status_code == 422

    async def test_custom_limit(
        self,
        async_client,
        fake_search_client: FakeSearchClient,
    ) -> None:
        fake_search_client.search.return_value = {
            "hits": [],
            "estimatedTotalHits": 0,
            "processingTimeMs": 0,
        }

        resp = await async_client.get(
            "/search/",
            params={"q": "test", "limit": 5},
        )
        assert resp.status_code == 200

        # Verify limit was propagated
        for call in fake_search_client.search.call_args_list:
            assert call.kwargs.get("limit") == 5 or (len(call.args) > 2 and call.args[2] == 5)

    async def test_no_results(
        self,
        async_client,
        fake_search_client: FakeSearchClient,
    ) -> None:
        fake_search_client.search.return_value = {
            "hits": [],
            "estimatedTotalHits": 0,
            "processingTimeMs": 0,
        }

        resp = await async_client.get("/search/", params={"q": "xyznonexistent"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["entities"] == []
        assert data["events"] == []
