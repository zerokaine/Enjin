# Enjin

> Open-source intelligence aggregation and visualization platform.
> Know your world. Hold power accountable.

---

## Vision

Enjin is an OSINT aggregation and visualization platform that transforms publicly available
information into structured, navigable intelligence. Starting with a geographic focus
(Denmark / Copenhagen), it scales outward — mapping how local events ripple into global
patterns, and maintaining accountability profiles on entities that hold significant societal
power: billionaires, governments, and law enforcement institutions.

The core thesis: **public information belongs to the public.** No actor should walk around
believing their actions are invisible simply because the connections are hard to see.
Enjin makes them visible.

---

## Core Pillars

### 1. Geographic Intelligence
Area-specific awareness: local news, events, technology activity, companies, and public
records — anchored to a location (initially Copenhagen/Denmark), expandable to any region.

### 2. Ripple Analysis
Local events do not stay local. Enjin maps how a corporate decision in Copenhagen connects
to a regulatory change in Brussels, which affects a supply chain in Rotterdam. Connections
are first-class citizens.

### 3. Entity Graph
Every piece of intelligence is structured as a graph: people, organizations, events, and
locations are nodes. Relationships, influences, ownership, and co-occurrences are edges.
The graph is queryable and visualizable.

### 4. Power Accountability (The Watchers)
A dedicated module for tracking entities with outsized societal influence — billionaires,
government ministries, law enforcement leadership — using exclusively public data:
financial disclosures, public contracts, corporate registries, parliamentary records,
public statements, and press coverage.

---

## Modules

| Module | Description |
|---|---|
| **Ingestor** | Crawlers, API clients, RSS consumers. Pulls raw data from public sources on a schedule. |
| **Extractor** | NLP pipeline: entity recognition, relationship extraction, geographic tagging, event classification. |
| **Graph Store** | Neo4j-backed entity/relationship graph. The intelligence core. |
| **Event Store** | PostgreSQL + PostGIS for time-series events with geographic coordinates. |
| **Search Index** | Meilisearch or Elasticsearch for full-text search across all ingested data. |
| **API Server** | FastAPI backend exposing graph queries, entity profiles, event feeds, and ripple traces. |
| **Globe UI** | Next.js frontend with Globe.gl (Three.js) 3D globe: arcs, heat maps, entity pins, timeline scrubber. |
| **Watcher Module** | Dedicated accountability profiles for tracked high-power entities. |
| **Alert Engine** | Rules-based and ML-assisted flagging when monitored entities appear in new contexts. |

---

## Data Sources

### News & Events
- **GDELT Project** — global event database, free, machine-readable, massive
- **NewsAPI** — aggregated news headlines
- **RSS Feeds** — DR (Danish Broadcasting), Politiken, Berlingske, The Guardian, Reuters
- **Common Crawl** — broad web archive for supplemental coverage

### Denmark / Copenhagen Specific
- **CVR (Det Centrale Virksomhedsregister)** — Danish Business Register, public API: companies, directors, ownership
- **Folketing** (Danish Parliament) — public records, voting history, committee memberships
- **Copenhagen Municipality Open Data** — local government data
- **Statsforvaltningen** — public administrative decisions

### EU & International Government
- **EUR-Lex** — EU legislation and decisions
- **OpenSecrets / FollowTheMoney equivalents** — political financing where available
- **World Bank Open Data**, **UN Data**

### Corporate & Financial
- **OpenCorporates API** — global company registry aggregator
- **Public company filings** (SEC EDGAR for US entities, Danish equivalents)
- **Wikidata** — structured entity data with cross-references

### Geographic
- **OpenStreetMap / Nominatim** — geocoding and reverse geocoding
- **Natural Earth** — country/region boundary data

### People & Organizations
- **Wikipedia / Wikidata** — baseline entity profiles
- **Parliamentary records** — public official biographies, roles, affiliations

---

## Entity Model (Graph Schema)

### Node Types
- `Person` — politician, executive, billionaire, law enforcement official
- `Organization` — company, government body, NGO, media outlet, political party
- `Event` — news story, legislative action, corporate filing, incident
- `Location` — country, city, region, specific address
- `Asset` — property, company stake, financial instrument (from public disclosures)

### Relationship Types
- `LOCATED_IN` (Person/Org → Location)
- `AFFILIATED_WITH` (Person → Org, with time range)
- `OWNS` / `CONTROLS` (Person/Org → Asset/Org)
- `AFFECTS` (Event → Location/Org/Person)
- `CONNECTED_TO` (Event → Event, Person → Person)
- `REPORTED_BY` (Event → Organization[media])
- `GOVERNS` (Org → Location)
- `EMPLOYS` (Org → Person)

---

## 3D Globe UI

Built with **Globe.gl** (Three.js under the hood):

- **Heat arcs** between locations when events are connected
- **Pulsing pins** for active event clusters (size = significance)
- **Heat map layer** for news density by region
- **Entity selection** — click a pin to open entity profile panel
- **Timeline scrubber** — scroll back in time to see historical connection patterns
- **Ripple mode** — select an event and trace its propagation outward across the globe
- **Watcher overlay** — toggle to highlight locations of tracked high-power entities

---

## Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| Frontend | Next.js + TypeScript | SSR, good ecosystem, React |
| 3D Visualization | Globe.gl + Three.js | Best globe-with-arcs library available |
| Backend API | Python + FastAPI | Rich OSINT/NLP ecosystem |
| Graph Database | Neo4j | Native graph queries (Cypher), entity relationships |
| Relational/Geo DB | PostgreSQL + PostGIS | Time-series events, geographic queries |
| Search | Meilisearch | Fast full-text search, easy setup |
| Task Queue | Celery + Redis | Background ingestion jobs, scheduling |
| NLP Pipeline | spaCy + Hugging Face | NER, relationship extraction, classification |
| Containerization | Docker + Docker Compose | Reproducible environment |

---

## Development Phases

### Phase 0 — Foundation
- [ ] Project structure: monorepo layout (`/api`, `/frontend`, `/ingestion`, `/data`)
- [ ] Docker Compose environment: Neo4j, PostgreSQL, Redis, Meilisearch, API
- [ ] Core data models and graph schema
- [ ] Basic ingestion scaffold (RSS feed consumer)
- [ ] CI setup

### Phase 1 — Data Layer
- [ ] Ingestor framework: pluggable source adapters
- [ ] Denmark-specific adapters: CVR API, Folketing records, Danish news RSS
- [ ] GDELT adapter for international event context
- [ ] Entity deduplication and normalization pipeline
- [ ] Basic graph population from ingested data

### Phase 2 — Intelligence Layer
- [ ] NLP pipeline: spaCy NER for person/org/location extraction from article text
- [ ] Geographic tagging: Nominatim geocoding of extracted locations
- [ ] Relationship inference: co-occurrence, explicit mention parsing
- [ ] Event classification: political / economic / social / legal / security
- [ ] Cross-event linkage: dedup and cluster related events

### Phase 3 — Globe UI
- [ ] Next.js project scaffold with TypeScript
- [ ] Globe.gl integration: base globe with location markers
- [ ] Arc rendering: draw connections between related events/locations
- [ ] Entity profile panel: sidebar with structured entity data
- [ ] Timeline scrubber: animate events over time
- [ ] Basic search: query entities and events

### Phase 4 — Watcher Module
- [ ] Watcher entity profiles: billionaires, government ministers, law enforcement heads
- [ ] Source-specific scrapers: public disclosures, company registry cross-references
- [ ] Activity feed per watched entity: all ingested events where entity appears
- [ ] Network graph: connections between watched entities and their organizations/assets
- [ ] Globe overlay: geographic footprint of watched entity activity

### Phase 5 — Ripple Analysis
- [ ] Ripple trace algorithm: given an event, find connected events by entity, location, topic
- [ ] Impact scoring: weight connections by temporal proximity, entity overlap, topic similarity
- [ ] Globe ripple animation: visual arc propagation from source event outward
- [ ] Pattern detection: recurring relationship patterns, anomaly flagging
- [ ] Export: structured reports, graph snapshots

---

## Scope Boundaries

**In scope (public data only):**
- Public news, press releases, RSS feeds
- Government and parliamentary public records
- Public corporate registries (CVR, OpenCorporates)
- Public financial disclosures
- Wikipedia / Wikidata
- Public social media posts from public accounts

**Out of scope:**
- Private communications or non-public data
- Any form of unauthorized access
- Personal data of private individuals (non-public figures)
- Real-time surveillance or tracking of individuals

---

## Initial Geographic Focus

**Denmark / Copenhagen** as the primary pilot region:
- Well-documented public data (CVR is excellent)
- Active tech ecosystem (game dev, fintech, cleantech)
- Clear government transparency norms
- EU membership = rich cross-border connection data
- Manageable scale for initial validation

Designed to expand to any region by adding source adapters.

---

## Name

**Enjin** — an engine for structured awareness. It processes raw public information and
outputs navigable intelligence, like a combustion engine converts raw fuel into directed
motion.
