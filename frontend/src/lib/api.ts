/* ------------------------------------------------------------------ */
/*  Enjin OSINT Platform - API Client                                  */
/* ------------------------------------------------------------------ */

import type {
  Entity,
  Event,
  EventFeed,
  SearchResult,
  Connection,
  Watcher,
  WatcherActivity,
  RippleGraph,
} from './types'

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${BASE_URL}${path}`

  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  if (!res.ok) {
    const body = await res.text().catch(() => 'Unknown error')
    throw new ApiError(res.status, `API ${res.status}: ${body}`)
  }

  // Handle 204 No Content
  if (res.status === 204) {
    return undefined as T
  }

  return res.json() as Promise<T>
}

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== '',
  )
  if (entries.length === 0) return ''
  return '?' + new URLSearchParams(
    entries.map(([k, v]) => [k, String(v)]),
  ).toString()
}

/* ------------------------------------------------------------------ */
/*  Search                                                             */
/* ------------------------------------------------------------------ */

export async function searchEntities(
  query: string,
  type?: string,
  limit: number = 20,
): Promise<SearchResult[]> {
  return request<SearchResult[]>(
    `/search${qs({ q: query, type, limit })}`,
  )
}

/* ------------------------------------------------------------------ */
/*  Entities                                                           */
/* ------------------------------------------------------------------ */

export async function getEntity(id: string): Promise<Entity> {
  return request<Entity>(`/entities/${encodeURIComponent(id)}`)
}

export async function getEntityConnections(
  id: string,
  depth: number = 1,
): Promise<Connection[]> {
  return request<Connection[]>(
    `/entities/${encodeURIComponent(id)}/connections${qs({ depth })}`,
  )
}

/* ------------------------------------------------------------------ */
/*  Events                                                             */
/* ------------------------------------------------------------------ */

export interface EventFilters {
  category?: string
  region?: string
  from?: string
  to?: string
  page?: number
  per_page?: number
}

export async function getEvents(
  filters: EventFilters = {},
): Promise<EventFeed> {
  return request<EventFeed>(`/events${qs(filters as Record<string, string>)}`)
}

export async function getEventFeed(
  category?: string,
  region?: string,
): Promise<EventFeed> {
  return request<EventFeed>(
    `/events/feed${qs({ category, region })}`,
  )
}

export async function getEvent(id: string): Promise<Event> {
  return request<Event>(`/events/${encodeURIComponent(id)}`)
}

/* ------------------------------------------------------------------ */
/*  Graph / Ripple                                                     */
/* ------------------------------------------------------------------ */

export async function getRipple(eventId: string): Promise<RippleGraph> {
  return request<RippleGraph>(
    `/graph/ripple/${encodeURIComponent(eventId)}`,
  )
}

/* ------------------------------------------------------------------ */
/*  Watchers                                                           */
/* ------------------------------------------------------------------ */

export async function getWatchers(): Promise<Watcher[]> {
  return request<Watcher[]>('/watchers')
}

export async function addWatcher(entityId: string): Promise<Watcher> {
  return request<Watcher>('/watchers', {
    method: 'POST',
    body: JSON.stringify({ entity_id: entityId }),
  })
}

export async function removeWatcher(watcherId: string): Promise<void> {
  return request<void>(
    `/watchers/${encodeURIComponent(watcherId)}`,
    { method: 'DELETE' },
  )
}

export async function getWatcherActivity(
  watcherId: string,
): Promise<WatcherActivity[]> {
  return request<WatcherActivity[]>(
    `/watchers/${encodeURIComponent(watcherId)}/activity`,
  )
}

/* ------------------------------------------------------------------ */
/*  SWR Fetcher                                                        */
/* ------------------------------------------------------------------ */

/**
 * Generic SWR-compatible fetcher. Pass to useSWR as the fetcher function.
 *
 * Usage: useSWR('/events?category=cyber', fetcher)
 */
export const fetcher = <T>(path: string): Promise<T> =>
  request<T>(path)
