'use client'

/* ------------------------------------------------------------------ */
/*  Enjin Dashboard - Primary OSINT Intelligence View                  */
/*                                                                     */
/*  Layout:                                                            */
/*    - Globe takes full screen                                        */
/*    - Left sidebar (collapsible): SearchBar + entity feed            */
/*    - Bottom bar: Timeline scrubber                                  */
/*    - Right panel (slides in): EntityPanel on selection              */
/*    - Top-right: WatcherOverlay toggle                               */
/* ------------------------------------------------------------------ */

import { useState, useCallback, useMemo, useEffect } from 'react'
import dynamic from 'next/dynamic'
import SearchBar from '@/components/SearchBar'
import EntityPanel from '@/components/EntityPanel'
import Timeline from '@/components/Timeline'
import WatcherOverlay from '@/components/WatcherOverlay'
import { useGlobeData } from '@/hooks/useGlobeData'
import { getEntity, addWatcher, removeWatcher, getWatchers } from '@/lib/api'
import type {
  Entity,
  GlobePoint,
  SearchResult,
  Watcher,
  TimeRange,
  EventCategory,
} from '@/lib/types'

/* ------------------------------------------------------------------ */
/*  Dynamic import for Globe (requires window/document)                */
/* ------------------------------------------------------------------ */

const Globe = dynamic(() => import('@/components/Globe'), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full flex items-center justify-center bg-enjin-dark">
      <div className="flex flex-col items-center gap-4">
        <div className="relative w-20 h-20">
          <div className="absolute inset-0 rounded-full border-2 border-enjin-blue/10" />
          <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-enjin-blue animate-spin" />
          <div className="absolute inset-2 rounded-full border border-enjin-purple/20" />
          <div className="absolute inset-2 rounded-full border border-transparent border-b-enjin-purple animate-spin" style={{ animationDirection: 'reverse', animationDuration: '1.5s' }} />
        </div>
        <div className="text-center">
          <p className="text-enjin-blue/60 text-sm font-mono tracking-wider uppercase">
            Initializing Globe
          </p>
          <p className="text-white/20 text-[10px] font-mono mt-1">
            Loading 3D visualization engine...
          </p>
        </div>
      </div>
    </div>
  ),
})

/* ------------------------------------------------------------------ */
/*  Placeholder data for visual demo                                   */
/* ------------------------------------------------------------------ */

const PLACEHOLDER_DENSITY = [
  2, 5, 3, 8, 12, 7, 4, 9, 15, 11, 6, 3, 8, 14, 10,
  5, 7, 13, 9, 4, 6, 11, 8, 3, 7, 10, 14, 6, 9, 5,
  3, 8, 12, 7, 4, 11, 15, 9, 6, 3, 5, 10, 8, 13, 7,
  4, 9, 6, 11, 8,
]

const DEFAULT_TIME_RANGE: TimeRange = {
  start: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000), // 30 days ago
  end: new Date(),
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function DashboardPage() {
  /* ---- State ---- */
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [selectedEntity, setSelectedEntity] = useState<Entity | null>(null)
  const [watcherMode, setWatcherMode] = useState(false)
  const [watchers, setWatchers] = useState<Watcher[]>([])
  const [timelinePosition, setTimelinePosition] = useState(1) // start at "now"
  const [timeRange, setTimeRange] = useState<TimeRange>(DEFAULT_TIME_RANGE)
  const [globeReady, setGlobeReady] = useState(false)

  /* ---- Globe data ---- */
  const { points, arcs, isLoading: isGlobeDataLoading } = useGlobeData({
    timeRange,
  })

  /* ---- Load watchers on mount ---- */
  useEffect(() => {
    getWatchers()
      .then(setWatchers)
      .catch(() => setWatchers([]))
  }, [])

  /* ---- Handlers ---- */

  const handlePointClick = useCallback(async (point: GlobePoint) => {
    try {
      const entity = await getEntity(point.id)
      setSelectedEntity(entity)
    } catch {
      // If the point isn't a direct entity, we still show info
      console.warn(`Could not load entity for point ${point.id}`)
    }
  }, [])

  const handleSearchSelect = useCallback(async (result: SearchResult) => {
    if (result.type === 'entity') {
      const entity = result.item as Entity
      setSelectedEntity(entity)
    } else {
      // For events, try to load the associated entity or show event details
      // For now, just try to get the entity
      try {
        const entity = await getEntity(result.item.id)
        setSelectedEntity(entity)
      } catch {
        // Event doesn't have a direct entity mapping
      }
    }
  }, [])

  const handleWatch = useCallback(async (entity: Entity) => {
    try {
      const watcher = await addWatcher(entity.id)
      setWatchers((prev) => [...prev, watcher])
    } catch (err) {
      console.error('Failed to add watcher:', err)
    }
  }, [])

  const handleRemoveWatcher = useCallback(async (watcherId: string) => {
    try {
      await removeWatcher(watcherId)
      setWatchers((prev) => prev.filter((w) => w.id !== watcherId))
    } catch (err) {
      console.error('Failed to remove watcher:', err)
    }
  }, [])

  const handleWatcherSelect = useCallback(async (watcher: Watcher) => {
    try {
      const entity = await getEntity(watcher.entity_id)
      setSelectedEntity(entity)
    } catch {
      console.warn(`Could not load entity for watcher ${watcher.id}`)
    }
  }, [])

  const handleCloseEntity = useCallback(() => {
    setSelectedEntity(null)
  }, [])

  /* ---- Render ---- */

  return (
    <div className="relative w-screen h-screen overflow-hidden">
      {/* ============================================================ */}
      {/*  Globe (full-screen background)                              */}
      {/* ============================================================ */}
      <div className="absolute inset-0 z-0">
        <Globe
          events={points}
          connections={arcs}
          onPointClick={handlePointClick}
          onGlobeReady={() => setGlobeReady(true)}
        />
      </div>

      {/* ============================================================ */}
      {/*  Top bar - branding + status                                 */}
      {/* ============================================================ */}
      <div className="absolute top-0 left-0 right-0 z-20 pointer-events-none">
        <div className="flex items-center justify-between px-4 py-3">
          {/* Logo / title */}
          <div className="pointer-events-auto flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="p-2 glass-panel rounded text-white/40 hover:text-white/70
                        transition-colors"
              aria-label="Toggle sidebar"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                {sidebarOpen ? (
                  <path strokeLinecap="round" strokeLinejoin="round" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
                )}
              </svg>
            </button>

            <div>
              <h1 className="text-sm font-bold tracking-[0.3em] uppercase text-glow-blue text-enjin-blue">
                Enjin
              </h1>
              <p className="text-[9px] text-white/20 uppercase tracking-[0.2em] -mt-0.5">
                Intelligence Engine
              </p>
            </div>
          </div>

          {/* Status indicators */}
          <div className="flex items-center gap-4 mr-32 pointer-events-auto">
            {/* Data status */}
            <div className="flex items-center gap-1.5">
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  isGlobeDataLoading
                    ? 'bg-enjin-amber animate-pulse'
                    : 'bg-enjin-green flicker'
                }`}
              />
              <span className="text-[10px] text-white/30 font-mono uppercase tracking-wider">
                {isGlobeDataLoading ? 'Syncing' : 'Live'}
              </span>
            </div>

            {/* Points count */}
            <span className="text-[10px] text-white/20 font-mono">
              {points.length} events
            </span>
          </div>
        </div>
      </div>

      {/* ============================================================ */}
      {/*  Left sidebar                                                */}
      {/* ============================================================ */}
      {sidebarOpen && (
        <div className="absolute top-16 left-0 bottom-28 w-80 z-20 animate-slide-in-left">
          <div className="h-full flex flex-col mx-3">
            {/* Search */}
            <div className="flex-shrink-0 mb-3">
              <SearchBar onSelect={handleSearchSelect} />
            </div>

            {/* Entity / event feed */}
            <div className="flex-1 overflow-y-auto glass-panel rounded">
              <div className="px-3 py-2 border-b border-white/5 flex items-center justify-between">
                <h2 className="text-[10px] uppercase tracking-[0.15em] text-white/30 font-bold">
                  Recent Events
                </h2>
                <span className="text-[10px] text-white/15 font-mono">
                  {points.length}
                </span>
              </div>

              {points.length === 0 && !isGlobeDataLoading ? (
                <div className="px-4 py-12 text-center">
                  <div className="w-10 h-10 mx-auto mb-3 rounded-full border border-white/5 flex items-center justify-center">
                    <svg className="w-5 h-5 text-white/10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                  <p className="text-xs text-white/20 font-mono">
                    No events in current view
                  </p>
                  <p className="text-[10px] text-white/10 font-mono mt-1">
                    Adjust time range or filters
                  </p>
                </div>
              ) : (
                <div className="divide-y divide-white/[0.03]">
                  {points.slice(0, 50).map((point) => (
                    <button
                      key={point.id}
                      onClick={() => handlePointClick(point)}
                      className="w-full text-left px-3 py-2.5 hover:bg-white/5
                                transition-colors group"
                    >
                      <div className="flex items-start gap-2.5">
                        {/* Color indicator */}
                        <div
                          className="flex-shrink-0 w-2 h-2 rounded-full mt-1.5"
                          style={{ backgroundColor: point.color }}
                        />

                        <div className="flex-1 min-w-0">
                          <p className="text-xs text-white/60 group-hover:text-white/80
                                       truncate transition-colors">
                            {point.label}
                          </p>
                          <div className="flex items-center gap-2 mt-0.5">
                            {point.category && (
                              <span className="text-[9px] text-white/25 uppercase tracking-wider">
                                {point.category}
                              </span>
                            )}
                            <span className="text-[9px] text-white/15 font-mono">
                              {point.lat.toFixed(1)}, {point.lng.toFixed(1)}
                            </span>
                          </div>
                        </div>

                        {/* Size indicator */}
                        <div
                          className="flex-shrink-0 w-1.5 rounded-full bg-white/10 mt-1"
                          style={{
                            height: `${Math.max(8, point.size * 20)}px`,
                            backgroundColor: `${point.color}40`,
                          }}
                        />
                      </div>
                    </button>
                  ))}
                </div>
              )}

              {isGlobeDataLoading && (
                <div className="px-4 py-6 text-center">
                  <div className="w-5 h-5 border-2 border-enjin-blue/20 border-t-enjin-blue rounded-full animate-spin mx-auto mb-2" />
                  <span className="text-[10px] text-white/20 font-mono">
                    Loading events...
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/*  Entity Panel (right slide-in)                               */}
      {/* ============================================================ */}
      <EntityPanel
        entity={selectedEntity}
        onClose={handleCloseEntity}
        onWatch={handleWatch}
      />

      {/* ============================================================ */}
      {/*  Watcher Overlay (top-right)                                 */}
      {/* ============================================================ */}
      <WatcherOverlay
        active={watcherMode}
        onToggle={() => setWatcherMode(!watcherMode)}
        watchers={watchers}
        onWatcherSelect={handleWatcherSelect}
        onRemoveWatcher={handleRemoveWatcher}
      />

      {/* ============================================================ */}
      {/*  Timeline (bottom bar)                                       */}
      {/* ============================================================ */}
      <Timeline
        range={timeRange}
        currentPosition={timelinePosition}
        onPositionChange={setTimelinePosition}
        eventDensity={PLACEHOLDER_DENSITY}
        onPlaybackChange={(playing, speed) => {
          // Could be used to control data refresh rate
        }}
        onRangeChange={setTimeRange}
      />

      {/* ============================================================ */}
      {/*  Keyboard shortcut hints (bottom-left, above timeline)       */}
      {/* ============================================================ */}
      <div className="absolute bottom-32 left-4 z-10 hidden lg:block pointer-events-none">
        <div className="flex flex-col gap-1 text-[9px] text-white/10 font-mono">
          <span>
            <kbd className="px-1 py-0.5 border border-white/10 rounded text-[8px]">S</kbd> Search
          </span>
          <span>
            <kbd className="px-1 py-0.5 border border-white/10 rounded text-[8px]">W</kbd> Watchers
          </span>
          <span>
            <kbd className="px-1 py-0.5 border border-white/10 rounded text-[8px]">ESC</kbd> Close
          </span>
        </div>
      </div>
    </div>
  )
}
