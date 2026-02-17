"""Pydantic schemas for intelligence events (stored in PostgreSQL + PostGIS)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class EventCategory(StrEnum):
    """Controlled vocabulary for event classification."""

    political = "political"
    economic = "economic"
    social = "social"
    legal = "legal"
    security = "security"
    technology = "technology"


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class EventCreate(BaseModel):
    """Payload accepted when creating a new event."""

    title: str = Field(..., min_length=1, max_length=500)
    summary: str | None = Field(default=None, max_length=5000)
    category: EventCategory | None = None
    occurred_at: datetime | None = Field(
        default=None, description="When the event actually happened (UTC)"
    )
    location_name: str | None = Field(default=None, max_length=300)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    source_url: str | None = Field(default=None, max_length=2048)
    metadata: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class EventResponse(BaseModel):
    """Single event returned to the client."""

    id: str
    title: str
    summary: str | None = None
    category: str | None = None
    occurred_at: datetime | None = None
    location_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    source_url: str | None = None
    created_at: datetime
    connections: list[dict] = Field(
        default_factory=list,
        description="Entities and other events connected to this event",
    )


class EventFeed(BaseModel):
    """Paginated list of events."""

    events: list[EventResponse]
    total: int
    page: int
    per_page: int
