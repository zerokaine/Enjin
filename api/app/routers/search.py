"""Unified search endpoint that queries Meilisearch across all indexes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.db.search import SearchClient, get_search_client

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/")
async def unified_search(
    q: str = Query(..., min_length=1, description="Search query"),
    index: str | None = Query(
        default=None,
        description="Restrict to a single index ('entities' or 'events'). "
        "Omit to search both.",
    ),
    type_filter: str | None = Query(
        default=None,
        description="Entity type filter (person, organization, location, asset)",
    ),
    category: str | None = Query(
        default=None,
        description="Event category filter",
    ),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """Search across entities and events using Meilisearch.

    Returns a combined result set when no *index* is specified, or scoped
    results when *index* is ``entities`` or ``events``.
    """
    search = get_search_client()

    results: dict[str, Any] = {
        "query": q,
        "entities": [],
        "events": [],
    }

    search_entities = index is None or index == SearchClient.ENTITIES_INDEX
    search_events = index is None or index == SearchClient.EVENTS_INDEX

    # --- Entities ---
    if search_entities:
        filters_parts: list[str] = []
        if type_filter:
            filters_parts.append(f"type = '{type_filter}'")
        entity_filter = " AND ".join(filters_parts) if filters_parts else None

        entity_results = search.search(
            query=q,
            index=SearchClient.ENTITIES_INDEX,
            limit=limit,
            filters=entity_filter,
        )
        results["entities"] = entity_results.get("hits", [])
        results["entity_total"] = entity_results.get("estimatedTotalHits", 0)
        results["entity_time_ms"] = entity_results.get("processingTimeMs", 0)

    # --- Events ---
    if search_events:
        event_filter_parts: list[str] = []
        if category:
            event_filter_parts.append(f"category = '{category}'")
        event_filter = " AND ".join(event_filter_parts) if event_filter_parts else None

        event_results = search.search(
            query=q,
            index=SearchClient.EVENTS_INDEX,
            limit=limit,
            filters=event_filter,
        )
        results["events"] = event_results.get("hits", [])
        results["event_total"] = event_results.get("estimatedTotalHits", 0)
        results["event_time_ms"] = event_results.get("processingTimeMs", 0)

    return results
