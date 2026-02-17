/* ------------------------------------------------------------------ */
/*  Enjin OSINT Platform - Core Type Definitions                      */
/* ------------------------------------------------------------------ */

/** Entity types supported by the platform */
export type EntityType = 'person' | 'organization' | 'location' | 'vessel' | 'asset' | 'unknown'

/** Event categories for classification */
export type EventCategory =
  | 'political'
  | 'military'
  | 'economic'
  | 'cyber'
  | 'social'
  | 'environmental'
  | 'criminal'
  | 'other'

/** Connection / relationship types between entities */
export type ConnectionType =
  | 'associate'
  | 'member_of'
  | 'subsidiary'
  | 'owner'
  | 'located_at'
  | 'involved_in'
  | 'funded_by'
  | 'allied_with'
  | 'rival'
  | 'other'

/* ------------------------------------------------------------------ */
/*  Domain Models                                                      */
/* ------------------------------------------------------------------ */

export interface Entity {
  id: string
  name: string
  type: EntityType
  metadata: Record<string, unknown>
  role?: string
  nationality?: string
  aliases?: string[]
  org_type?: string
  country?: string
  latitude?: number
  longitude?: number
  description?: string
  created_at?: string
  updated_at?: string
}

export interface Event {
  id: string
  title: string
  summary?: string
  category?: EventCategory
  occurred_at?: string
  location_name?: string
  latitude?: number
  longitude?: number
  source_url?: string
  connections?: Connection[]
  severity?: number
  tags?: string[]
  created_at?: string
}

export interface Connection {
  id?: string
  from_id: string
  to_id: string
  type: ConnectionType
  metadata?: Record<string, unknown>
  label?: string
  weight?: number
}

/* ------------------------------------------------------------------ */
/*  Globe Visualization Models                                         */
/* ------------------------------------------------------------------ */

export interface GlobePoint {
  lat: number
  lng: number
  label: string
  size: number
  color: string
  id: string
  category?: EventCategory
  altitude?: number
}

export interface GlobeArc {
  startLat: number
  startLng: number
  endLat: number
  endLng: number
  color: string
  label?: string
  stroke?: number
}

export interface GlobeLabel {
  lat: number
  lng: number
  text: string
  size?: number
  color?: string
}

/* ------------------------------------------------------------------ */
/*  Watcher System                                                     */
/* ------------------------------------------------------------------ */

export interface Watcher {
  id: string
  entity_id: string
  name: string
  type: EntityType
  description?: string
  active: boolean
  last_activity?: string
  alert_count?: number
  latitude?: number
  longitude?: number
  created_at?: string
}

export interface WatcherActivity {
  id: string
  watcher_id: string
  event_id: string
  event_title: string
  occurred_at: string
  severity?: number
}

/* ------------------------------------------------------------------ */
/*  Search & Feed                                                      */
/* ------------------------------------------------------------------ */

export interface SearchResult {
  type: 'entity' | 'event'
  item: Entity | Event
  score?: number
}

export interface EventFeed {
  events: Event[]
  total: number
  page: number
  per_page: number
}

/* ------------------------------------------------------------------ */
/*  Timeline                                                           */
/* ------------------------------------------------------------------ */

export interface TimeRange {
  start: Date
  end: Date
}

export interface TimeBucket {
  timestamp: string
  count: number
}

/* ------------------------------------------------------------------ */
/*  API Response Wrappers                                              */
/* ------------------------------------------------------------------ */

export interface ApiResponse<T> {
  data: T
  message?: string
  status: number
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  per_page: number
  has_more: boolean
}

/* ------------------------------------------------------------------ */
/*  Ripple Graph (event propagation)                                   */
/* ------------------------------------------------------------------ */

export interface RippleNode {
  id: string
  name: string
  type: EntityType
  depth: number
}

export interface RippleEdge {
  source: string
  target: string
  type: ConnectionType
  weight?: number
}

export interface RippleGraph {
  nodes: RippleNode[]
  edges: RippleEdge[]
  center_event_id: string
}
