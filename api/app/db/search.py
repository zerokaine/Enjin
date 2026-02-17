"""Meilisearch client wrapper for full-text search across entities and events."""

from __future__ import annotations

import logging
from typing import Any

import meilisearch

logger = logging.getLogger(__name__)

# Module-level singleton
_instance: SearchClient | None = None


class SearchClient:
    """Async-friendly wrapper around the Meilisearch Python SDK.

    Note: the ``meilisearch`` Python client is synchronous, but its operations
    are fast HTTP calls to a local service.  We keep a thin wrapper so the rest
    of the codebase has a consistent interface and can be swapped to an async
    implementation later.
    """

    # Index names
    ENTITIES_INDEX = "entities"
    EVENTS_INDEX = "events"

    def __init__(self, url: str, master_key: str) -> None:
        self._url = url
        self._master_key = master_key
        self._client: meilisearch.Client | None = None

    # -- lifecycle ------------------------------------------------------------

    def connect(self) -> None:
        """Create the underlying HTTP client."""
        self._client = meilisearch.Client(self._url, self._master_key)
        logger.info("Meilisearch client created (%s)", self._url)

    def close(self) -> None:
        """Release resources (no-op for sync client, kept for interface parity)."""
        self._client = None

    @property
    def client(self) -> meilisearch.Client:
        assert self._client is not None, "SearchClient.connect() has not been called"
        return self._client

    # -- index management -----------------------------------------------------

    def init_indexes(self) -> None:
        """Create or update the expected indexes with proper settings."""
        # Entities index
        self.client.create_index(self.ENTITIES_INDEX, {"primaryKey": "id"})
        self.client.index(self.ENTITIES_INDEX).update_settings(
            {
                "searchableAttributes": ["name", "aliases", "role", "org_type", "region"],
                "filterableAttributes": ["type", "country", "nationality", "org_type"],
                "sortableAttributes": ["name"],
            }
        )

        # Events index
        self.client.create_index(self.EVENTS_INDEX, {"primaryKey": "id"})
        self.client.index(self.EVENTS_INDEX).update_settings(
            {
                "searchableAttributes": ["title", "summary", "location_name", "category"],
                "filterableAttributes": ["category", "location_name"],
                "sortableAttributes": ["occurred_at", "created_at"],
            }
        )
        logger.info("Meilisearch indexes initialised")

    # -- entity operations ----------------------------------------------------

    def index_entity(self, entity: dict[str, Any]) -> None:
        """Add or update a single entity document in the search index."""
        self.client.index(self.ENTITIES_INDEX).add_documents([entity])

    def index_entities(self, entities: list[dict[str, Any]]) -> None:
        """Bulk-add entities to the search index."""
        if entities:
            self.client.index(self.ENTITIES_INDEX).add_documents(entities)

    # -- event operations -----------------------------------------------------

    def index_event(self, event: dict[str, Any]) -> None:
        """Add or update a single event document in the search index."""
        # Meilisearch requires string or int primary keys
        doc = {**event}
        if "id" in doc and not isinstance(doc["id"], (str, int)):
            doc["id"] = str(doc["id"])
        # Convert datetime objects to ISO strings for JSON serialisation
        for key in ("occurred_at", "created_at", "updated_at"):
            if key in doc and hasattr(doc[key], "isoformat"):
                doc[key] = doc[key].isoformat()
        self.client.index(self.EVENTS_INDEX).add_documents([doc])

    def index_events(self, events: list[dict[str, Any]]) -> None:
        """Bulk-add events to the search index."""
        if events:
            docs = []
            for event in events:
                doc = {**event}
                if "id" in doc and not isinstance(doc["id"], (str, int)):
                    doc["id"] = str(doc["id"])
                for key in ("occurred_at", "created_at", "updated_at"):
                    if key in doc and hasattr(doc[key], "isoformat"):
                        doc[key] = doc[key].isoformat()
                docs.append(doc)
            self.client.index(self.EVENTS_INDEX).add_documents(docs)

    # -- search ---------------------------------------------------------------

    def search(
        self,
        query: str,
        index: str = ENTITIES_INDEX,
        limit: int = 20,
        filters: str | None = None,
    ) -> dict[str, Any]:
        """Execute a search query against the specified index.

        Parameters
        ----------
        query:
            Free-text search string.
        index:
            Name of the Meilisearch index to query.
        limit:
            Maximum number of results.
        filters:
            Optional Meilisearch filter expression, e.g.
            ``"type = 'person' AND country = 'US'"``.

        Returns
        -------
        dict
            Raw Meilisearch response containing ``hits``, ``estimatedTotalHits``,
            ``query``, ``processingTimeMs``, etc.
        """
        params: dict[str, Any] = {"limit": limit}
        if filters:
            params["filter"] = filters
        return self.client.index(index).search(query, params)


# ---------------------------------------------------------------------------
# Singleton helpers
# ---------------------------------------------------------------------------

def get_search_client() -> SearchClient:
    """Return the module-level SearchClient singleton."""
    if _instance is None:
        raise RuntimeError(
            "SearchClient has not been initialised — call init_search_client() first"
        )
    return _instance


def init_search_client(url: str, master_key: str) -> SearchClient:
    """Create, connect, and store the module-level singleton."""
    global _instance
    _instance = SearchClient(url, master_key)
    _instance.connect()
    _instance.init_indexes()
    return _instance


def close_search_client() -> None:
    """Shut down and discard the module-level singleton."""
    global _instance
    if _instance is not None:
        _instance.close()
        _instance = None
