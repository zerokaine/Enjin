"""Celery tasks for the Enjin ingestion pipeline.

Task chain: fetch -> extract -> geocode -> normalise -> store

Each task is self-contained with proper error handling and logging so
that failures in one source or one item do not block the rest of the
pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from celery import chain as celery_chain
from neo4j import GraphDatabase
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters import ADAPTER_REGISTRY, get_adapter
from app.adapters.base import RawItem
from app.config import settings
from app.main import celery_app
from app.pipeline.extractor import EntityExtractor, ExtractedEntity
from app.pipeline.geocoder import Geocoder, GeoResult
from app.pipeline.normalizer import EntityNormalizer, NormalisedEntity

logger = logging.getLogger(__name__)

# ── helpers to bridge async adapters into sync Celery tasks ──────────
_loop: asyncio.AbstractEventLoop | None = None


def _get_loop() -> asyncio.AbstractEventLoop:
    """Return a dedicated event loop for running async adapter code."""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
    return _loop


def _run_async(coro: Any) -> Any:
    """Run an async coroutine from a synchronous Celery task."""
    loop = _get_loop()
    return loop.run_until_complete(coro)


# ═══════════════════════════════════════════════════════════════════════
# PostgreSQL helpers (raw item storage)
# ═══════════════════════════════════════════════════════════════════════
_engine = create_async_engine(settings.postgres_dsn, pool_size=5, max_overflow=5)

_ENSURE_TABLE_SQL = """\
CREATE TABLE IF NOT EXISTS raw_items (
    id              BIGSERIAL PRIMARY KEY,
    source_adapter  TEXT NOT NULL,
    external_id     TEXT NOT NULL UNIQUE,
    title           TEXT NOT NULL,
    content         TEXT,
    summary         TEXT,
    authors         JSONB DEFAULT '[]',
    published_at    TIMESTAMPTZ,
    source_url      TEXT,
    metadata        JSONB DEFAULT '{}',
    processed       BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
"""

_UPSERT_SQL = """\
INSERT INTO raw_items (source_adapter, external_id, title, content, summary,
                       authors, published_at, source_url, metadata)
VALUES (:source_adapter, :external_id, :title, :content, :summary,
        :authors, :published_at, :source_url, :metadata)
ON CONFLICT (external_id) DO NOTHING;
"""

_SELECT_UNPROCESSED_SQL = """\
SELECT id, source_adapter, external_id, title, content, summary,
       authors, published_at, source_url, metadata
FROM raw_items
WHERE processed = FALSE
ORDER BY created_at ASC
LIMIT :batch_size;
"""

_MARK_PROCESSED_SQL = """\
UPDATE raw_items SET processed = TRUE WHERE id = :item_id;
"""


async def _ensure_table() -> None:
    async with _engine.begin() as conn:
        await conn.execute(sa_text(_ENSURE_TABLE_SQL))


async def _store_raw_items(items: list[RawItem]) -> int:
    """Persist raw items to PostgreSQL.  Returns count of newly inserted rows."""
    await _ensure_table()
    inserted = 0
    async with _engine.begin() as conn:
        for item in items:
            result = await conn.execute(
                sa_text(_UPSERT_SQL),
                {
                    "source_adapter": item.source_adapter,
                    "external_id": item.external_id,
                    "title": item.title,
                    "content": item.content,
                    "summary": item.summary,
                    "authors": json.dumps(item.authors),
                    "published_at": item.published_at,
                    "source_url": item.source_url,
                    "metadata": json.dumps(item.metadata),
                },
            )
            inserted += result.rowcount
    return inserted


async def _load_unprocessed(batch_size: int = 200) -> list[dict[str, Any]]:
    await _ensure_table()
    async with _engine.connect() as conn:
        result = await conn.execute(
            sa_text(_SELECT_UNPROCESSED_SQL), {"batch_size": batch_size}
        )
        rows = result.mappings().all()
        return [dict(r) for r in rows]


async def _mark_processed(item_id: int) -> None:
    async with _engine.begin() as conn:
        await conn.execute(sa_text(_MARK_PROCESSED_SQL), {"item_id": item_id})


# ═══════════════════════════════════════════════════════════════════════
# Neo4j helpers (entity / relationship storage)
# ═══════════════════════════════════════════════════════════════════════
def _get_neo4j_driver():
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )


def _store_entities_neo4j(
    entities: list[NormalisedEntity],
    source_item: dict[str, Any],
    geo_results: dict[str, GeoResult],
) -> None:
    """Create / merge entity nodes and relationship edges in Neo4j."""
    driver = _get_neo4j_driver()
    try:
        with driver.session() as session:
            # Merge the source document node
            session.run(
                """
                MERGE (d:Document {external_id: $external_id})
                SET d.title      = $title,
                    d.source_url  = $source_url,
                    d.adapter     = $adapter,
                    d.published_at = $published_at
                """,
                external_id=source_item["external_id"],
                title=source_item["title"],
                source_url=source_item.get("source_url"),
                adapter=source_item["source_adapter"],
                published_at=str(source_item.get("published_at", "")),
            )

            for ent in entities:
                label = _neo4j_label(ent.type)

                # Merge the entity node
                session.run(
                    f"""
                    MERGE (e:{label} {{name: $name}})
                    SET e.type        = $type,
                        e.occurrences = COALESCE(e.occurrences, 0) + $occ
                    """,
                    name=ent.name,
                    type=ent.type,
                    occ=ent.occurrences,
                )

                # Add geo data if available
                geo = geo_results.get(ent.name)
                if geo:
                    session.run(
                        f"""
                        MATCH (e:{label} {{name: $name}})
                        SET e.latitude  = $lat,
                            e.longitude = $lon,
                            e.country   = $country,
                            e.region    = $region
                        """,
                        name=ent.name,
                        lat=geo.latitude,
                        lon=geo.longitude,
                        country=geo.country,
                        region=geo.region,
                    )

                # Create MENTIONED_IN relationship to the document
                session.run(
                    f"""
                    MATCH (e:{label} {{name: $name}})
                    MATCH (d:Document {{external_id: $doc_id}})
                    MERGE (e)-[r:MENTIONED_IN]->(d)
                    SET r.occurrences = $occ
                    """,
                    name=ent.name,
                    doc_id=source_item["external_id"],
                    occ=ent.occurrences,
                )

            # Create CO_OCCURS relationships between entities in the same doc
            entity_names = [(ent.name, _neo4j_label(ent.type)) for ent in entities]
            for i, (name_a, label_a) in enumerate(entity_names):
                for name_b, label_b in entity_names[i + 1 :]:
                    session.run(
                        f"""
                        MATCH (a:{label_a} {{name: $name_a}})
                        MATCH (b:{label_b} {{name: $name_b}})
                        MERGE (a)-[r:CO_OCCURS]->(b)
                        SET r.weight = COALESCE(r.weight, 0) + 1,
                            r.last_seen = $now
                        """,
                        name_a=name_a,
                        name_b=name_b,
                        now=datetime.now(UTC).isoformat(),
                    )
    finally:
        driver.close()


def _neo4j_label(entity_type: str) -> str:
    """Map Enjin entity types to Neo4j node labels."""
    return {
        "person": "Person",
        "org": "Organization",
        "location": "Location",
    }.get(entity_type, "Entity")


# ═══════════════════════════════════════════════════════════════════════
# Celery tasks
# ═══════════════════════════════════════════════════════════════════════

@celery_app.task(
    bind=True,
    name="app.tasks.ingest.fetch_all_sources",
    max_retries=3,
    default_retry_delay=60,
)
def fetch_all_sources(self, adapter_name: str | None = None) -> dict[str, Any]:
    """Dispatch a ``fetch_source`` task for every active adapter.

    If *adapter_name* is given, only that adapter is dispatched.
    """
    logger.info("fetch_all_sources: starting (adapter_name=%s)", adapter_name)

    names = [adapter_name] if adapter_name else list(ADAPTER_REGISTRY.keys())
    dispatched: list[str] = []

    for name in names:
        if name not in ADAPTER_REGISTRY:
            logger.warning("fetch_all_sources: unknown adapter '%s', skipping", name)
            continue
        try:
            # Build default source_config from settings
            source_config = _default_config_for(name)
            fetch_source.delay(adapter_name=name, source_config=source_config)
            dispatched.append(name)
        except Exception:
            logger.exception("fetch_all_sources: failed to dispatch '%s'", name)

    return {"dispatched": dispatched, "count": len(dispatched)}


@celery_app.task(
    bind=True,
    name="app.tasks.ingest.fetch_source",
    max_retries=3,
    default_retry_delay=120,
    acks_late=True,
)
def fetch_source(
    self,
    adapter_name: str,
    source_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a single adapter and persist its raw items to PostgreSQL."""
    logger.info("fetch_source: running adapter '%s'", adapter_name)
    try:
        adapter = get_adapter(adapter_name, source_config)
        items: list[RawItem] = _run_async(adapter.fetch())
        logger.info("fetch_source: adapter '%s' returned %d items", adapter_name, len(items))

        if items:
            inserted = _run_async(_store_raw_items(items))
            logger.info(
                "fetch_source: stored %d new items from '%s'", inserted, adapter_name
            )
        else:
            inserted = 0

        return {
            "adapter": adapter_name,
            "fetched": len(items),
            "inserted": inserted,
        }

    except Exception as exc:
        logger.exception("fetch_source: adapter '%s' failed", adapter_name)
        raise self.retry(exc=exc) from None


@celery_app.task(
    bind=True,
    name="app.tasks.ingest.process_raw_items",
    max_retries=2,
    default_retry_delay=30,
)
def process_raw_items(self, batch_size: int = 200) -> dict[str, Any]:
    """Load unprocessed items and run the NLP + geocoding pipeline.

    For each raw item:
      1. Extract entities (NER via spaCy)
      2. Geocode location entities
      3. Normalise and deduplicate entities
      4. Store entities and relationships in Neo4j
      5. Mark the item as processed in PostgreSQL
    """
    logger.info("process_raw_items: loading up to %d unprocessed items", batch_size)
    rows = _run_async(_load_unprocessed(batch_size))

    if not rows:
        logger.info("process_raw_items: nothing to process")
        return {"processed": 0}

    extractor = EntityExtractor()
    geocoder = Geocoder()
    normalizer = EntityNormalizer()

    processed_count = 0
    error_count = 0

    for row in rows:
        try:
            _process_single_item(row, extractor, geocoder, normalizer)
            _run_async(_mark_processed(row["id"]))
            processed_count += 1
        except Exception:
            error_count += 1
            logger.exception(
                "process_raw_items: failed to process item %s (id=%s)",
                row.get("external_id"),
                row.get("id"),
            )

    logger.info(
        "process_raw_items: processed=%d, errors=%d", processed_count, error_count
    )
    return {"processed": processed_count, "errors": error_count}


def _process_single_item(
    row: dict[str, Any],
    extractor: EntityExtractor,
    geocoder: Geocoder,
    normalizer: EntityNormalizer,
) -> None:
    """Run the full pipeline on a single raw item."""
    # 1. Build text corpus from title + summary + content
    parts = [row.get("title", ""), row.get("summary") or "", row.get("content") or ""]
    text = " ".join(p for p in parts if p)

    # 2. Extract entities
    raw_entities: list[ExtractedEntity] = extractor.extract_entities(text)
    if not raw_entities:
        logger.debug("No entities found in item %s", row.get("external_id"))
        return

    # 3. Normalise and deduplicate
    normalised: list[NormalisedEntity] = normalizer.deduplicate_entities(raw_entities)

    # 4. Geocode location entities
    geo_results: dict[str, GeoResult] = {}
    for ent in normalised:
        if ent.type == "location":
            result = _run_async(geocoder.geocode(ent.name))
            if result:
                geo_results[ent.name] = result

    # 5. Store in Neo4j
    _store_entities_neo4j(normalised, row, geo_results)

    logger.debug(
        "Processed item %s: %d entities, %d geocoded",
        row.get("external_id"),
        len(normalised),
        len(geo_results),
    )


# ═══════════════════════════════════════════════════════════════════════
# Convenience: full pipeline for a single adapter (fetch -> process)
# ═══════════════════════════════════════════════════════════════════════

@celery_app.task(name="app.tasks.ingest.run_full_pipeline")
def run_full_pipeline(adapter_name: str) -> str:
    """Chain fetch + process for a single adapter.

    Usage::

        from app.tasks.ingest import run_full_pipeline
        run_full_pipeline.delay("rss")
    """
    source_config = _default_config_for(adapter_name)
    workflow = celery_chain(
        fetch_source.s(adapter_name=adapter_name, source_config=source_config),
        process_raw_items.si(),
    )
    result = workflow.apply_async()
    return f"Pipeline dispatched for '{adapter_name}' (chain id: {result.id})"


# ── config helpers ───────────────────────────────────────────────────
def _default_config_for(adapter_name: str) -> dict[str, Any]:
    """Build a default source_config dict from global settings."""
    if adapter_name == "rss":
        return {"feed_urls": settings.rss_feed_urls}
    if adapter_name == "gdelt":
        return {
            "base_url": settings.gdelt_base_url,
            "focus_countries": settings.gdelt_focus_countries,
        }
    if adapter_name == "cvr":
        return {
            "api_url": settings.cvr_api_url,
            "search_terms": [],  # populated per-query from the API layer
        }
    return {}
