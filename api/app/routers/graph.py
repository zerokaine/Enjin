"""Graph-centric analytical endpoints — pathfinding, ripple traces, clustering."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.db.neo4j import get_graph_db
from app.services.graph import GraphService

router = APIRouter(prefix="/graph", tags=["graph"])


# ---------------------------------------------------------------------------
# GET /graph/connections — shortest path between two entities
# ---------------------------------------------------------------------------

@router.get("/connections")
async def get_connections(
    from_id: str = Query(..., description="Source entity ID"),
    to_id: str = Query(..., description="Target entity ID"),
    max_depth: int = Query(default=6, ge=1, le=10, description="Max path length"),
) -> dict[str, Any]:
    """Find the shortest connection path between two entities in the graph."""
    svc = GraphService(get_graph_db())
    path = await svc.find_shortest_path(from_id, to_id, max_depth=max_depth)

    if path is None:
        raise HTTPException(
            status_code=404,
            detail=f"No path found between {from_id} and {to_id} within {max_depth} hops",
        )

    return path


# ---------------------------------------------------------------------------
# GET /graph/ripple/{event_id} — event ripple trace
# ---------------------------------------------------------------------------

@router.get("/ripple/{event_id}")
async def get_ripple(
    event_id: str,
    max_hops: int = Query(default=3, ge=1, le=6, description="Max outward hops"),
) -> dict[str, Any]:
    """Trace the connected events and entities radiating outward from an event.

    This powers the "ripple map" visualisation on the frontend — showing how an
    event propagates through the entity/event graph.
    """
    svc = GraphService(get_graph_db())
    ripple = await svc.get_ripple_trace(event_id, max_hops=max_hops)

    if ripple is None:
        raise HTTPException(status_code=404, detail="Event not found in graph")

    return ripple


# ---------------------------------------------------------------------------
# GET /graph/cluster/{location} — geographic entity/event cluster
# ---------------------------------------------------------------------------

@router.get("/cluster/{location}")
async def get_cluster(
    location: str,
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(default=50, ge=1, le=500, description="Search radius in km"),
) -> dict[str, Any]:
    """Return the entity and event cluster around a geographic point.

    *location* is used as a human-readable label; the actual spatial query
    runs against *lat*/*lon* with the given *radius_km*.
    """
    svc = GraphService(get_graph_db())
    cluster = await svc.get_area_cluster(lat, lon, radius_km)

    return {
        "location": location,
        "center": {"latitude": lat, "longitude": lon},
        "radius_km": radius_km,
        **cluster,
    }
