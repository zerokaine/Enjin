"""Async Neo4j driver wrapper for graph operations."""

from __future__ import annotations

import logging
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase

logger = logging.getLogger(__name__)

# Module-level singleton — initialised at application startup.
_instance: GraphDB | None = None


class GraphDB:
    """Thin async wrapper around the official Neo4j Python driver.

    All public methods acquire their own session and are safe to call
    concurrently from FastAPI request handlers.
    """

    def __init__(self, uri: str, user: str, password: str) -> None:
        self._uri = uri
        self._user = user
        self._password = password
        self._driver: AsyncDriver | None = None

    # -- lifecycle ------------------------------------------------------------

    async def connect(self) -> None:
        """Create the underlying driver and verify connectivity."""
        self._driver = AsyncGraphDatabase.driver(
            self._uri,
            auth=(self._user, self._password),
            max_connection_pool_size=50,
        )
        await self._driver.verify_connectivity()
        logger.info("Neo4j connection established (%s)", self._uri)

    async def close(self) -> None:
        """Gracefully shut down the driver."""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")

    # -- low-level query ------------------------------------------------------

    async def execute(
        self,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Run a Cypher query and return all result records as dicts."""
        assert self._driver is not None, "GraphDB.connect() has not been called"
        async with self._driver.session() as session:
            result = await session.run(query, parameters=params or {})
            records = await result.data()
            return records

    # -- entity CRUD ----------------------------------------------------------

    async def find_entity(self, entity_id: str) -> dict[str, Any] | None:
        """Return a single entity node by its ``id`` property."""
        query = """
        MATCH (e {id: $entity_id})
        RETURN e{.*, _labels: labels(e)} AS entity
        """
        rows = await self.execute(query, {"entity_id": entity_id})
        return rows[0]["entity"] if rows else None

    async def find_connections(
        self,
        entity_id: str,
        depth: int = 1,
    ) -> list[dict[str, Any]]:
        """Return nodes connected to *entity_id* up to *depth* hops away."""
        query = """
        MATCH (source {id: $entity_id})-[r*1..$depth]-(target)
        WITH DISTINCT target, r
        RETURN target{.*, _labels: labels(target)} AS node,
               [rel IN r | {type: type(rel), props: properties(rel)}] AS rels
        """
        return await self.execute(query, {"entity_id": entity_id, "depth": depth})

    async def create_entity(
        self,
        label: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a new node with the given label and properties."""
        safe_label = label.capitalize()
        query = f"""
        CREATE (e:{safe_label} $props)
        SET e.created_at = datetime()
        RETURN e{{.*, _labels: labels(e)}} AS entity
        """
        rows = await self.execute(query, {"props": properties})
        return rows[0]["entity"]

    async def create_relationship(
        self,
        from_id: str,
        to_id: str,
        rel_type: str,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a directed edge between two existing nodes."""
        safe_type = rel_type.upper().replace(" ", "_")
        query = f"""
        MATCH (a {{id: $from_id}}), (b {{id: $to_id}})
        CREATE (a)-[r:{safe_type} $props]->(b)
        SET r.created_at = datetime()
        RETURN type(r) AS type, properties(r) AS props
        """
        rows = await self.execute(
            query,
            {"from_id": from_id, "to_id": to_id, "props": properties or {}},
        )
        return rows[0] if rows else {}

    async def search_entities(
        self,
        query_text: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Full-text search across all entity types.

        Requires a full-text index named ``entitySearch`` created with::

            CREATE FULLTEXT INDEX entitySearch FOR (n:Person|Organization|Location|Asset)
            ON EACH [n.name, n.aliases]
        """
        query = """
        CALL db.index.fulltext.queryNodes('entitySearch', $text)
        YIELD node, score
        RETURN node{.*, _labels: labels(node)} AS entity, score
        ORDER BY score DESC
        LIMIT $limit
        """
        return await self.execute(query, {"text": query_text, "limit": limit})


# ---------------------------------------------------------------------------
# Singleton helpers (used during app lifespan)
# ---------------------------------------------------------------------------

def get_graph_db() -> GraphDB:
    """Return the module-level GraphDB singleton.

    Raises ``RuntimeError`` if the singleton has not been initialised yet.
    """
    if _instance is None:
        raise RuntimeError("GraphDB has not been initialised — call init_graph_db() first")
    return _instance


async def init_graph_db(uri: str, user: str, password: str) -> GraphDB:
    """Create, connect, and store the module-level singleton."""
    global _instance
    _instance = GraphDB(uri, user, password)
    await _instance.connect()
    return _instance


async def close_graph_db() -> None:
    """Shut down and discard the module-level singleton."""
    global _instance
    if _instance is not None:
        await _instance.close()
        _instance = None
