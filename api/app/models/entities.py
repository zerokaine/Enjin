"""Pydantic schemas for graph entities (nodes in Neo4j)."""

from __future__ import annotations

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class EntityBase(BaseModel):
    """Fields shared by every entity type stored in the graph."""

    id: str = Field(..., description="Unique entity identifier (UUID or slug)")
    name: str = Field(..., min_length=1, description="Display name")
    type: str = Field(..., description="Entity type discriminator")
    metadata: dict = Field(default_factory=dict, description="Arbitrary key-value metadata")


# ---------------------------------------------------------------------------
# Concrete entity types
# ---------------------------------------------------------------------------

class Person(EntityBase):
    """An individual human being."""

    type: str = "person"
    role: str | None = Field(default=None, description="Primary role / title")
    nationality: str | None = Field(default=None, description="ISO-3166-1 alpha-2 country code")
    aliases: list[str] = Field(default_factory=list, description="Known alternative names")


class Organization(EntityBase):
    """A company, government body, NGO, media outlet, or political party."""

    type: str = "organization"
    org_type: str | None = Field(
        default=None,
        description="Sub-type: company | government | ngo | media | party",
    )
    country: str | None = Field(default=None, description="HQ country (ISO-3166-1 alpha-2)")
    aliases: list[str] = Field(default_factory=list, description="Known alternative names")


class Location(EntityBase):
    """A named geographic place."""

    type: str = "location"
    country: str | None = Field(default=None, description="Country (ISO-3166-1 alpha-2)")
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    region: str | None = Field(default=None, description="Sub-national region or province")


class Asset(EntityBase):
    """A trackable asset (financial instrument, property, vessel, etc.)."""

    type: str = "asset"
    asset_type: str | None = Field(
        default=None,
        description="E.g. real_estate | vessel | aircraft | account | crypto",
    )
    value: float | None = Field(default=None, description="Estimated value")
    currency: str | None = Field(default=None, description="ISO-4217 currency code")
    owner_id: str | None = Field(default=None, description="Entity ID of current owner")


# ---------------------------------------------------------------------------
# Response wrappers
# ---------------------------------------------------------------------------

class EntityResponse(BaseModel):
    """Full entity payload returned to the client, including graph context."""

    entity: EntityBase
    relationships: list[dict] = Field(
        default_factory=list,
        description="Edges connected to this entity",
    )
    events: list[dict] = Field(
        default_factory=list,
        description="Recent events involving this entity",
    )
