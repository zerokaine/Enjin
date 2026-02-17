"""Watchlist endpoints — track entities and their activity over time."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.db.neo4j import get_graph_db
from app.db.postgres import Watcher, get_session

router = APIRouter(prefix="/watchers", tags=["watchers"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class WatcherCreate(BaseModel):
    """Payload to add an entity to the watch list."""

    entity_id: str = Field(..., description="Graph entity ID to watch")
    entity_name: str | None = Field(default=None, description="Cached display name")
    entity_type: str | None = Field(default=None, description="Entity type for quick filtering")
    notes: str | None = Field(default=None, description="User notes about why this is watched")


class WatcherResponse(BaseModel):
    id: str
    entity_id: str
    entity_name: str | None = None
    entity_type: str | None = None
    notes: str | None = None
    active: bool
    created_at: str
    updated_at: str


def _row_to_response(row: Watcher) -> WatcherResponse:
    return WatcherResponse(
        id=str(row.id),
        entity_id=row.entity_id,
        entity_name=row.entity_name,
        entity_type=row.entity_type,
        notes=row.notes,
        active=row.active,
        created_at=row.created_at.isoformat() if row.created_at else "",
        updated_at=row.updated_at.isoformat() if row.updated_at else "",
    )


# ---------------------------------------------------------------------------
# GET /watchers — list all watched entities
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[WatcherResponse])
async def list_watchers(
    active_only: bool = Query(default=True, description="Only return active watchers"),
) -> list[WatcherResponse]:
    """Return all current watch-list entries."""
    async with get_session() as session:
        stmt = select(Watcher).order_by(Watcher.created_at.desc())
        if active_only:
            stmt = stmt.where(Watcher.active.is_(True))
        result = await session.execute(stmt)
        rows = result.scalars().all()

    return [_row_to_response(r) for r in rows]


# ---------------------------------------------------------------------------
# GET /watchers/{watcher_id} — single watcher with activity feed
# ---------------------------------------------------------------------------

@router.get("/{watcher_id}", response_model=dict[str, Any])
async def get_watcher(watcher_id: str) -> dict[str, Any]:
    """Return watcher profile along with a recent activity feed from the graph."""
    async with get_session() as session:
        result = await session.execute(
            select(Watcher).where(Watcher.id == watcher_id)
        )
        row = result.scalar_one_or_none()

    if row is None:
        raise HTTPException(status_code=404, detail="Watcher not found")

    # Fetch recent events connected to the watched entity in the graph
    activity: list[dict] = []
    try:
        graph = get_graph_db()
        q = """
        MATCH (e {id: $entity_id})-[r]-(ev:Event)
        RETURN ev{.*, _labels: labels(ev)} AS event, type(r) AS rel_type
        ORDER BY ev.occurred_at DESC
        LIMIT 30
        """
        rows = await graph.execute(q, {"entity_id": row.entity_id})
        activity = [{"event": r["event"], "relationship": r["rel_type"]} for r in rows]
    except Exception:
        pass

    return {
        "watcher": _row_to_response(row).model_dump(),
        "activity": activity,
    }


# ---------------------------------------------------------------------------
# POST /watchers — add entity to watch list
# ---------------------------------------------------------------------------

@router.post("/", response_model=WatcherResponse, status_code=201)
async def create_watcher(payload: WatcherCreate) -> WatcherResponse:
    """Add an entity to the watch list."""
    # Resolve the entity name from the graph if not provided
    entity_name = payload.entity_name
    entity_type = payload.entity_type
    if not entity_name:
        try:
            graph = get_graph_db()
            entity = await graph.find_entity(payload.entity_id)
            if entity:
                entity_name = entity.get("name")
                entity_type = entity_type or entity.get("type")
        except Exception:
            pass

    watcher = Watcher(
        id=uuid.uuid4(),
        entity_id=payload.entity_id,
        entity_name=entity_name,
        entity_type=entity_type,
        notes=payload.notes,
        active=True,
    )

    async with get_session() as session:
        session.add(watcher)
        await session.flush()
        await session.refresh(watcher)

    return _row_to_response(watcher)


# ---------------------------------------------------------------------------
# DELETE /watchers/{watcher_id} — remove from watch list
# ---------------------------------------------------------------------------

@router.delete("/{watcher_id}", status_code=204)
async def delete_watcher(watcher_id: str) -> None:
    """Remove an entity from the watch list (hard delete)."""
    async with get_session() as session:
        result = await session.execute(
            delete(Watcher).where(Watcher.id == watcher_id)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Watcher not found")


# ---------------------------------------------------------------------------
# GET /watchers/{watcher_id}/activity — recent activity feed
# ---------------------------------------------------------------------------

@router.get("/{watcher_id}/activity")
async def get_watcher_activity(
    watcher_id: str,
    limit: int = Query(default=30, ge=1, le=100),
) -> list[dict[str, Any]]:
    """Return recent graph activity (events, new connections) for the watched entity."""
    async with get_session() as session:
        result = await session.execute(
            select(Watcher).where(Watcher.id == watcher_id)
        )
        row = result.scalar_one_or_none()

    if row is None:
        raise HTTPException(status_code=404, detail="Watcher not found")

    graph = get_graph_db()

    # Recent events
    event_query = """
    MATCH (e {id: $entity_id})-[r]-(ev:Event)
    RETURN ev{.*, _labels: labels(ev)} AS event, type(r) AS rel_type
    ORDER BY ev.occurred_at DESC
    LIMIT $limit
    """
    event_rows = await graph.execute(
        event_query, {"entity_id": row.entity_id, "limit": limit}
    )

    # Recent relationship changes (newest nodes connected)
    rel_query = """
    MATCH (e {id: $entity_id})-[r]-(n)
    WHERE NOT n:Event
    RETURN n{.*, _labels: labels(n)} AS node, type(r) AS rel_type,
           r.created_at AS connected_at
    ORDER BY r.created_at DESC
    LIMIT $limit
    """
    rel_rows = await graph.execute(
        rel_query, {"entity_id": row.entity_id, "limit": limit}
    )

    activity: list[dict[str, Any]] = []
    for r in event_rows:
        activity.append({"type": "event", "data": r["event"], "relationship": r["rel_type"]})
    for r in rel_rows:
        activity.append(
            {
                "type": "connection",
                "data": r["node"],
                "relationship": r["rel_type"],
                "connected_at": r.get("connected_at"),
            }
        )

    # Sort combined activity by timestamp (best-effort)
    activity.sort(
        key=lambda a: a.get("data", {}).get("occurred_at") or a.get("connected_at") or "",
        reverse=True,
    )

    return activity[:limit]


# ---------------------------------------------------------------------------
# GET /watchers/{watcher_id}/network — full network graph
# ---------------------------------------------------------------------------

@router.get("/{watcher_id}/network")
async def get_watcher_network(
    watcher_id: str,
    depth: int = Query(default=2, ge=1, le=4),
) -> dict[str, Any]:
    """Return the full network graph surrounding the watched entity."""
    async with get_session() as session:
        result = await session.execute(
            select(Watcher).where(Watcher.id == watcher_id)
        )
        row = result.scalar_one_or_none()

    if row is None:
        raise HTTPException(status_code=404, detail="Watcher not found")

    graph = get_graph_db()
    from app.services.graph import GraphService

    svc = GraphService(graph)
    network = await svc.get_entity_network(row.entity_id, depth=depth)

    return {
        "watcher_id": watcher_id,
        "entity_id": row.entity_id,
        "depth": depth,
        **network,
    }
