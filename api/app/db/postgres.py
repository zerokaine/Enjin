"""SQLAlchemy async engine, session factory, and ORM models for PostgreSQL + PostGIS."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship

from app.config import get_settings

# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""

    pass


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------


class RawItem(Base):
    """Ingested raw intelligence item before normalisation."""

    __tablename__ = "raw_items"

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_name = Column(String(200), nullable=False, index=True)
    source_url = Column(Text, nullable=True)
    title = Column(Text, nullable=True)
    body = Column(Text, nullable=True)
    raw_json = Column(JSONB, nullable=True)
    fetched_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed = Column(Boolean, nullable=False, default=False, index=True)

    __table_args__ = (
        Index("ix_raw_items_fetched", "fetched_at"),
    )


class Event(Base):
    """Normalised intelligence event with optional geospatial point."""

    __tablename__ = "events"

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    category = Column(String(50), nullable=True, index=True)
    occurred_at = Column(DateTime(timezone=True), nullable=True, index=True)
    location_name = Column(String(300), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    geom = Column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=True,
        comment="PostGIS point derived from lat/lon",
    )
    source_url = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    sources = relationship("Source", back_populates="event", lazy="selectin")

    __table_args__ = (
        Index("ix_events_occurred", "occurred_at"),
        Index("ix_events_category", "category"),
        Index(
            "ix_events_geom",
            "geom",
            postgresql_using="gist",
        ),
    )


class Source(Base):
    """External reference / citation linked to an event."""

    __tablename__ = "sources"

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    url = Column(Text, nullable=False)
    title = Column(Text, nullable=True)
    publisher = Column(String(300), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    credibility_score = Column(Float, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    event = relationship("Event", back_populates="sources")


class Watcher(Base):
    """A watched entity — the user wants to track changes and activity."""

    __tablename__ = "watchers"

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entity_id = Column(String(200), nullable=False, unique=True, index=True)
    entity_name = Column(String(500), nullable=True)
    entity_type = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("ix_watchers_entity", "entity_id"),
    )


# ---------------------------------------------------------------------------
# Engine & session management
# ---------------------------------------------------------------------------

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return (and lazily create) the global async engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.postgres_dsn,
            echo=False,
            pool_size=20,
            max_overflow=10,
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return (and lazily create) the global session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session and handle commit / rollback."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_postgres() -> None:
    """Verify the connection pool is live (called during app lifespan)."""
    engine = get_engine()
    async with engine.begin() as conn:
        # Quick connectivity check
        await conn.run_sync(lambda sync_conn: None)


async def close_postgres() -> None:
    """Dispose of the async engine."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
