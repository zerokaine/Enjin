"""Enjin OSINT Platform — FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db.neo4j import close_graph_db, init_graph_db
from app.db.postgres import close_postgres, init_postgres
from app.db.search import close_search_client, init_search_client
from app.routers import entities, events, graph, search, watchers

logger = logging.getLogger("enjin")

# ---------------------------------------------------------------------------
# Application-scoped Redis connection (exposed via app.state)
# ---------------------------------------------------------------------------

_redis: aioredis.Redis | None = None


# ---------------------------------------------------------------------------
# Lifespan — connect / disconnect all backing services
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage the lifecycle of external service connections.

    Connections are established when the application starts and torn down
    gracefully on shutdown.
    """
    global _redis
    settings = get_settings()

    # --- startup ---
    logger.info("Starting Enjin API — connecting to backing services...")

    # Neo4j
    try:
        await init_graph_db(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
        )
        logger.info("Neo4j connected")
    except Exception:
        logger.exception("Failed to connect to Neo4j — graph features will be unavailable")

    # PostgreSQL
    try:
        await init_postgres()
        logger.info("PostgreSQL connected")
    except Exception:
        logger.exception("Failed to connect to PostgreSQL — event storage unavailable")

    # Redis
    try:
        _redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        await _redis.ping()
        app.state.redis = _redis
        logger.info("Redis connected")
    except Exception:
        logger.exception("Failed to connect to Redis — caching unavailable")
        _redis = None

    # Meilisearch
    try:
        init_search_client(url=settings.meili_url, master_key=settings.meili_master_key)
        logger.info("Meilisearch connected")
    except Exception:
        logger.exception("Failed to connect to Meilisearch — search unavailable")

    logger.info("Enjin API startup complete")

    yield

    # --- shutdown ---
    logger.info("Shutting down Enjin API...")

    await close_graph_db()
    await close_postgres()
    close_search_client()

    if _redis is not None:
        await _redis.close()
        _redis = None

    logger.info("All connections closed — goodbye")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Enjin API",
    description="Backend API for the Enjin OSINT intelligence platform.",
    version="0.1.0",
    lifespan=lifespan,
)

# -- Middleware ---------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Open for development; lock down in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- Routers ------------------------------------------------------------------

app.include_router(entities.router)
app.include_router(events.router)
app.include_router(graph.router)
app.include_router(search.router)
app.include_router(watchers.router)


# -- Root & health endpoints --------------------------------------------------

@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    """Landing probe — returns service identity."""
    return {"name": "Enjin API", "version": "0.1.0"}


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str | dict[str, str]]:
    """Health check that reports the status of each backing service."""
    statuses: dict[str, str] = {}

    # Neo4j
    try:
        from app.db.neo4j import get_graph_db

        gdb = get_graph_db()
        await gdb.execute("RETURN 1")
        statuses["neo4j"] = "ok"
    except Exception as exc:
        statuses["neo4j"] = f"error: {exc}"

    # PostgreSQL
    try:
        from app.db.postgres import get_session

        async with get_session() as session:
            from sqlalchemy import text

            await session.execute(text("SELECT 1"))
        statuses["postgres"] = "ok"
    except Exception as exc:
        statuses["postgres"] = f"error: {exc}"

    # Redis
    try:
        if _redis is not None:
            await _redis.ping()
            statuses["redis"] = "ok"
        else:
            statuses["redis"] = "not connected"
    except Exception as exc:
        statuses["redis"] = f"error: {exc}"

    # Meilisearch
    try:
        from app.db.search import get_search_client

        client = get_search_client()
        client.client.health()
        statuses["meilisearch"] = "ok"
    except Exception as exc:
        statuses["meilisearch"] = f"error: {exc}"

    overall = "healthy" if all(v == "ok" for v in statuses.values()) else "degraded"
    return {"status": overall, "services": statuses}
