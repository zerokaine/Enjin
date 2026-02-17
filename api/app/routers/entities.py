"""CRUD and graph-query endpoints for entities."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.db.neo4j import get_graph_db
from app.db.search import get_search_client
from app.models.entities import (
    Asset,
    EntityBase,
    EntityResponse,
    Location,
    Organization,
    Person,
)

router = APIRouter(prefix="/entities", tags=["entities"])

# Map type names to their Pydantic models for validation
_TYPE_MAP: dict[str, type[EntityBase]] = {
    "person": Person,
    "organization": Organization,
    "location": Location,
    "asset": Asset,
}


# ---------------------------------------------------------------------------
# GET /entities — list entities
# ---------------------------------------------------------------------------


@router.get("/", response_model=list[dict[str, Any]])
async def list_entities(
    type: str | None = Query(default=None, description="Filter by entity type"),
    q: str | None = Query(default=None, description="Text search within entity names"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> list[dict[str, Any]]:
    """Return a paginated list of entities, optionally filtered by type."""
    graph = get_graph_db()

    if q:
        # Delegate to full-text search
        results = await graph.search_entities(q, limit=per_page)
        entities = [r["entity"] for r in results]
        if type:
            entities = [e for e in entities if e.get("type") == type]
        return entities

    # Cypher-based listing with optional label filter
    skip = (page - 1) * per_page
    if type:
        label = type.capitalize()
        query = f"""
        MATCH (e:{label})
        RETURN e{{.*, _labels: labels(e)}} AS entity
        ORDER BY e.name
        SKIP $skip LIMIT $limit
        """
    else:
        query = """
        MATCH (e)
        WHERE any(l IN labels(e) WHERE l IN ['Person','Organization','Location','Asset'])
        RETURN e{.*, _labels: labels(e)} AS entity
        ORDER BY e.name
        SKIP $skip LIMIT $limit
        """

    rows = await graph.execute(query, {"skip": skip, "limit": per_page})
    return [r["entity"] for r in rows]


# ---------------------------------------------------------------------------
# GET /entities/{entity_id} — single entity with context
# ---------------------------------------------------------------------------


@router.get("/{entity_id}", response_model=EntityResponse)
async def get_entity(entity_id: str) -> EntityResponse:
    """Return full entity details including relationships and recent events."""
    graph = get_graph_db()

    entity = await graph.find_entity(entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Fetch first-degree relationships
    connections = await graph.find_connections(entity_id, depth=1)
    relationships = []
    for conn in connections:
        relationships.append(
            {
                "target": conn["node"],
                "edges": conn.get("rels", []),
            }
        )

    # Fetch recent events linked to this entity
    event_query = """
    MATCH (e {id: $entity_id})-[r]-(ev:Event)
    RETURN ev{.*, _labels: labels(ev)} AS event, type(r) AS rel_type
    ORDER BY ev.occurred_at DESC
    LIMIT 20
    """
    event_rows = await graph.execute(event_query, {"entity_id": entity_id})
    events = [{"event": row["event"], "relationship": row["rel_type"]} for row in event_rows]

    return EntityResponse(entity=entity, relationships=relationships, events=events)


# ---------------------------------------------------------------------------
# GET /entities/{entity_id}/connections — connection graph
# ---------------------------------------------------------------------------


@router.get("/{entity_id}/connections")
async def get_entity_connections(
    entity_id: str,
    depth: int = Query(default=1, ge=1, le=5, description="Number of hops"),
) -> dict[str, Any]:
    """Return the subgraph of connections around an entity."""
    graph = get_graph_db()

    entity = await graph.find_entity(entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    connections = await graph.find_connections(entity_id, depth=depth)

    # Build a deduplicated node + edge structure for the frontend
    nodes: dict[str, dict] = {entity_id: entity}
    edges: list[dict] = []

    for conn in connections:
        node = conn["node"]
        node_id = node.get("id", "")
        nodes[node_id] = node
        for rel in conn.get("rels", []):
            edges.append(rel)

    return {
        "center": entity_id,
        "depth": depth,
        "nodes": list(nodes.values()),
        "edges": edges,
    }


# ---------------------------------------------------------------------------
# POST /entities — create a new entity
# ---------------------------------------------------------------------------


@router.post("/", response_model=dict[str, Any], status_code=201)
async def create_entity(payload: EntityBase) -> dict[str, Any]:
    """Create a new entity node in the graph."""
    graph = get_graph_db()

    # Assign an ID if the caller did not supply one
    props = payload.model_dump(exclude_none=True)
    if not props.get("id"):
        props["id"] = str(uuid.uuid4())

    entity_type = props.pop("type", "Entity")
    label = entity_type.capitalize()

    created = await graph.create_entity(label, props)

    # Index in Meilisearch
    try:
        search = get_search_client()
        search.index_entity({**props, "type": entity_type})
    except Exception:
        pass  # Search indexing is best-effort

    return created
