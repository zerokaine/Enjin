'use client'

/* ------------------------------------------------------------------ */
/*  useGlobeData - Fetches and transforms events for globe rendering   */
/* ------------------------------------------------------------------ */

import useSWR from 'swr'
import { fetcher } from '@/lib/api'
import type {
  EventFeed,
  GlobePoint,
  GlobeArc,
  EventCategory,
  TimeRange,
} from '@/lib/types'

/** Refresh interval in milliseconds */
const REFRESH_INTERVAL = 30_000

/** Color mapping for event categories */
const CATEGORY_COLORS: Record<EventCategory, string> = {
  political: '#7b2fff',
  military: '#ff3366',
  economic: '#ffaa00',
  cyber: '#00d4ff',
  social: '#00ff88',
  environmental: '#00ff88',
  criminal: '#ff3366',
  other: '#ffffff',
}

/** Default color for events without a category */
const DEFAULT_COLOR = '#00d4ff'

/** Severity-to-size mapping */
function severityToSize(severity?: number): number {
  const s = severity ?? 3
  return 0.3 + (s / 10) * 0.9 // Range: 0.3 - 1.2
}

/* ------------------------------------------------------------------ */
/*  Hook                                                               */
/* ------------------------------------------------------------------ */

interface UseGlobeDataOptions {
  category?: EventCategory
  region?: string
  timeRange?: TimeRange
}

interface UseGlobeDataReturn {
  points: GlobePoint[]
  arcs: GlobeArc[]
  isLoading: boolean
  error: Error | undefined
  mutate: () => void
}

export function useGlobeData(
  options: UseGlobeDataOptions = {},
): UseGlobeDataReturn {
  const { category, region, timeRange } = options

  // Build query string
  const params = new URLSearchParams()
  if (category) params.set('category', category)
  if (region) params.set('region', region)
  if (timeRange?.start) params.set('from', timeRange.start.toISOString())
  if (timeRange?.end) params.set('to', timeRange.end.toISOString())

  const queryString = params.toString()
  const endpoint = `/events/feed${queryString ? `?${queryString}` : ''}`

  const { data, error, isLoading, mutate } = useSWR<EventFeed>(
    endpoint,
    fetcher,
    {
      refreshInterval: REFRESH_INTERVAL,
      revalidateOnFocus: false,
      dedupingInterval: 5_000,
      errorRetryCount: 3,
      errorRetryInterval: 5_000,
      fallbackData: { events: [], total: 0, page: 1, per_page: 50 },
    },
  )

  // Transform events into globe points
  const points: GlobePoint[] = (data?.events ?? [])
    .filter((e) => e.latitude != null && e.longitude != null)
    .map((event) => ({
      lat: event.latitude!,
      lng: event.longitude!,
      label: event.title,
      size: severityToSize(event.severity),
      color: CATEGORY_COLORS[event.category as EventCategory] ?? DEFAULT_COLOR,
      id: event.id,
      category: event.category as EventCategory | undefined,
      altitude: 0.01 + (event.severity ?? 3) / 100,
    }))

  // Build arcs from event connections
  const arcs: GlobeArc[] = buildArcs(data?.events ?? [], points)

  return {
    points,
    arcs,
    isLoading,
    error,
    mutate: () => {
      mutate()
    },
  }
}

/* ------------------------------------------------------------------ */
/*  Arc Builder                                                        */
/* ------------------------------------------------------------------ */

/**
 * Builds arcs between events that share connections.
 * Each connection in an event references another entity; when two events
 * share overlapping connection targets we draw an arc between them.
 */
function buildArcs(
  events: EventFeed['events'],
  points: GlobePoint[],
): GlobeArc[] {
  const arcs: GlobeArc[] = []
  const pointMap = new Map(points.map((p) => [p.id, p]))

  for (const event of events) {
    if (!event.connections) continue

    for (const conn of event.connections) {
      const source = pointMap.get(event.id)
      // Try to find the target event in our point list
      const targetId = conn.to_id === event.id ? conn.from_id : conn.to_id
      const target = pointMap.get(targetId)

      if (source && target) {
        arcs.push({
          startLat: source.lat,
          startLng: source.lng,
          endLat: target.lat,
          endLng: target.lng,
          color: source.color,
          label: conn.label ?? conn.type,
          stroke: conn.weight ?? 1,
        })
      }
    }
  }

  return arcs
}

export default useGlobeData
