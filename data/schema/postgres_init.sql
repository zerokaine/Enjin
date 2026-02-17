-- Enjin PostgreSQL Schema with PostGIS

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Raw ingested articles/items before graph extraction
CREATE TABLE raw_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_adapter VARCHAR(64) NOT NULL,
    source_url TEXT,
    external_id VARCHAR(256),
    title TEXT NOT NULL,
    content TEXT,
    summary TEXT,
    authors TEXT[],
    published_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    processed BOOLEAN DEFAULT FALSE,
    UNIQUE(source_adapter, external_id)
);

-- Extracted events with geographic coordinates
CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    graph_id VARCHAR(64) UNIQUE,
    title TEXT NOT NULL,
    summary TEXT,
    category VARCHAR(32),
    occurred_at TIMESTAMPTZ,
    location_name TEXT,
    coordinates GEOMETRY(Point, 4326),
    source_item_id UUID REFERENCES raw_items(id),
    confidence FLOAT DEFAULT 1.0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Watcher profiles
CREATE TABLE watchers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    graph_id VARCHAR(64) UNIQUE NOT NULL,
    name TEXT NOT NULL,
    type VARCHAR(32) NOT NULL,
    description TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Watcher alert rules
CREATE TABLE watcher_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    watcher_id UUID REFERENCES watchers(id) ON DELETE CASCADE,
    rule_type VARCHAR(32) NOT NULL,
    pattern JSONB NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Ingestion source configuration
CREATE TABLE sources (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    adapter VARCHAR(64) NOT NULL,
    name TEXT NOT NULL,
    url TEXT,
    config JSONB DEFAULT '{}',
    schedule_cron VARCHAR(64) DEFAULT '*/30 * * * *',
    active BOOLEAN DEFAULT TRUE,
    last_fetched_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_raw_items_source ON raw_items(source_adapter);
CREATE INDEX idx_raw_items_published ON raw_items(published_at DESC);
CREATE INDEX idx_raw_items_processed ON raw_items(processed) WHERE NOT processed;
CREATE INDEX idx_events_category ON events(category);
CREATE INDEX idx_events_occurred ON events(occurred_at DESC);
CREATE INDEX idx_events_coordinates ON events USING GIST(coordinates);
CREATE INDEX idx_watchers_type ON watchers(type);
CREATE INDEX idx_sources_adapter ON sources(adapter);
