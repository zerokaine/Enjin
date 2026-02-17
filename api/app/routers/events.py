"""CRUD and feed endpoints for intelligence events."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.sql import and_

from app.db.postgres import Event, get_session
from app.db.search import get_search_client
from app.models.events import EventCreate, EventFeed, EventResponse

router = APIRouter(prefix="/events", tags=["events"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_response(row: Event, connections: list[dict] | None = None) -> EventResponse:
    """Convert an ORM Event row to the API response schema."""
    return EventResponse(
        id=str(row.id),
        title=row.title,
        summary=row.summary,
        category=row.category,
        occurred_at=row.occurred_at,
        location_name=row.location_name,
        latitude=row.latitude,
        longitude=row.longitude,
        source_url=row.source_url,
        created_at=row.created_at,
        connections=connections or [],
    )


# ---------------------------------------------------------------------------
# GET /events/feed — real-time event feed (must be above /{event_id})
# ---------------------------------------------------------------------------

@router.get("/feed", response_model=EventFeed)
async def event_feed(
    category: str | None = Query(default=None),
    region: str | None = Query(default=None, description="Filter by location_name substring"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> EventFeed:
    """Return the most recent events, optionally filtered by category or region."""
    offset = (page - 1) * per_page

    async with get_session() as session:
        conditions = []
        if category:
            conditions.append(Event.category == category)
        if region:
            conditions.append(Event.location_name.ilike(f"%{region}%"))

        where = and_(*conditions) if conditions else True

        # Total count
        count_q = select(func.count()).select_from(Event).where(where)
        total_result = await session.execute(count_q)
        total = total_result.scalar() or 0

        # Paginated results, newest first
        data_q = (
            select(Event)
            .where(where)
            .order_by(Event.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        result = await session.execute(data_q)
        rows = result.scalars().all()

    return EventFeed(
        events=[_row_to_response(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
    )


# ---------------------------------------------------------------------------
# GET /events — list with filters
# ---------------------------------------------------------------------------

@router.get("/", response_model=EventFeed)
async def list_events(
    category: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None, description="Start of date range (UTC)"),
    date_to: datetime | None = Query(default=None, description="End of date range (UTC)"),
    bbox_sw_lat: float | None = Query(default=None, description="Bounding box SW latitude"),
    bbox_sw_lon: float | None = Query(default=None, description="Bounding box SW longitude"),
    bbox_ne_lat: float | None = Query(default=None, description="Bounding box NE latitude"),
    bbox_ne_lon: float | None = Query(default=None, description="Bounding box NE longitude"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> EventFeed:
    """Return events matching the supplied filters."""
    offset = (page - 1) * per_page

    async with get_session() as session:
        conditions = []

        if category:
            conditions.append(Event.category == category)
        if date_from:
            conditions.append(Event.occurred_at >= date_from)
        if date_to:
            conditions.append(Event.occurred_at <= date_to)

        # Bounding box filter using PostGIS
        has_bbox = all(
            v is not None for v in (bbox_sw_lat, bbox_sw_lon, bbox_ne_lat, bbox_ne_lon)
        )
        if has_bbox:
            bbox_wkt = (
                f"POLYGON(({bbox_sw_lon} {bbox_sw_lat}, "
                f"{bbox_ne_lon} {bbox_sw_lat}, "
                f"{bbox_ne_lon} {bbox_ne_lat}, "
                f"{bbox_sw_lon} {bbox_ne_lat}, "
                f"{bbox_sw_lon} {bbox_sw_lat}))"
            )
            conditions.append(
                func.ST_Within(
                    Event.geom,
                    func.ST_GeomFromText(bbox_wkt, 4326),
                )
            )

        where = and_(*conditions) if conditions else True

        count_q = select(func.count()).select_from(Event).where(where)
        total_result = await session.execute(count_q)
        total = total_result.scalar() or 0

        data_q = (
            select(Event)
            .where(where)
            .order_by(Event.occurred_at.desc().nullslast())
            .offset(offset)
            .limit(per_page)
        )
        result = await session.execute(data_q)
        rows = result.scalars().all()

    return EventFeed(
        events=[_row_to_response(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
    )


# ---------------------------------------------------------------------------
# GET /events/{event_id} — single event detail
# ---------------------------------------------------------------------------

@router.get("/{event_id}", response_model=EventResponse)
async def get_event(event_id: str) -> EventResponse:
    """Return a single event with connected entities."""
    async with get_session() as session:
        result = await session.execute(
            select(Event).where(Event.id == event_id)
        )
        row = result.scalar_one_or_none()

    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")

    # Fetch graph connections from Neo4j
    connections: list[dict] = []
    try:
        from app.db.neo4j import get_graph_db

        graph = get_graph_db()
        conn_query = """
        MATCH (ev:Event {id: $event_id})-[r]-(n)
        RETURN n{.*, _labels: labels(n)} AS node, type(r) AS rel_type
        LIMIT 50
        """
        conn_rows = await graph.execute(conn_query, {"event_id": event_id})
        connections = [
            {"entity": cr["node"], "relationship": cr["rel_type"]} for cr in conn_rows
        ]
    except Exception:
        pass  # Graph enrichment is best-effort

    return _row_to_response(row, connections=connections)


# ---------------------------------------------------------------------------
# POST /events — create a new event
# ---------------------------------------------------------------------------

@router.post("/", response_model=EventResponse, status_code=201)
async def create_event(payload: EventCreate) -> EventResponse:
    """Persist a new event in PostgreSQL and index it in Meilisearch."""
    event_id = uuid.uuid4()

    new_event = Event(
        id=event_id,
        title=payload.title,
        summary=payload.summary,
        category=payload.category.value if payload.category else None,
        occurred_at=payload.occurred_at,
        location_name=payload.location_name,
        latitude=payload.latitude,
        longitude=payload.longitude,
        source_url=payload.source_url,
        metadata_=payload.metadata,
    )

    # Build PostGIS point if coordinates are provided
    if payload.latitude is not None and payload.longitude is not None:
        new_event.geom = func.ST_SetSRID(
            func.ST_MakePoint(payload.longitude, payload.latitude), 4326
        )

    async with get_session() as session:
        session.add(new_event)
        await session.flush()
        await session.refresh(new_event)

    # Index in Meilisearch (best-effort)
    try:
        search = get_search_client()
        search.index_event(
            {
                "id": str(event_id),
                "title": payload.title,
                "summary": payload.summary,
                "category": payload.category.value if payload.category else None,
                "occurred_at": payload.occurred_at.isoformat() if payload.occurred_at else None,
                "location_name": payload.location_name,
            }
        )
    except Exception:
        pass

    return _row_to_response(new_event)
