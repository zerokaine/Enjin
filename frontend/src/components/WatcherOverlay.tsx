'use client'

/* ------------------------------------------------------------------ */
/*  WatcherOverlay - Toggleable overlay for watched entities           */
/* ------------------------------------------------------------------ */

import { useState } from 'react'
import type { Watcher, EntityType } from '@/lib/types'

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface WatcherOverlayProps {
  active: boolean
  onToggle: () => void
  watchers: Watcher[]
  onWatcherSelect: (watcher: Watcher) => void
  onRemoveWatcher?: (watcherId: string) => void
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

const TYPE_COLORS: Record<EntityType, string> = {
  person: 'bg-enjin-blue',
  organization: 'bg-enjin-purple',
  location: 'bg-enjin-green',
  vessel: 'bg-enjin-amber',
  asset: 'bg-enjin-red',
  unknown: 'bg-white/30',
}

function formatRelativeTime(dateStr?: string): string {
  if (!dateStr) return 'No activity'

  const now = Date.now()
  const then = new Date(dateStr).getTime()
  const diffMs = now - then

  const minutes = Math.floor(diffMs / 60_000)
  if (minutes < 1) return 'Just now'
  if (minutes < 60) return `${minutes}m ago`

  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`

  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d ago`

  const months = Math.floor(days / 30)
  return `${months}mo ago`
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function WatcherOverlay({
  active,
  onToggle,
  watchers,
  onWatcherSelect,
  onRemoveWatcher,
}: WatcherOverlayProps) {
  const [filter, setFilter] = useState<'all' | 'active' | 'alerts'>('all')

  const filteredWatchers = watchers.filter((w) => {
    if (filter === 'active') return w.active
    if (filter === 'alerts') return (w.alert_count ?? 0) > 0
    return true
  })

  const totalAlerts = watchers.reduce((sum, w) => sum + (w.alert_count ?? 0), 0)

  return (
    <div className="fixed top-4 right-4 z-50">
      {/* Toggle button */}
      <button
        onClick={onToggle}
        className={`relative flex items-center gap-2 px-3 py-2 rounded
                   transition-all duration-200
                   ${
                     active
                       ? 'glass-panel border-enjin-blue/40 text-enjin-blue glow-blue'
                       : 'glass-panel text-white/40 hover:text-white/60 hover:border-white/20'
                   }`}
        aria-label="Toggle watcher overlay"
      >
        {/* Eye icon */}
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          {active ? (
            <>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            </>
          ) : (
            <path strokeLinecap="round" strokeLinejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
          )}
        </svg>

        <span className="text-xs font-mono uppercase tracking-wider hidden sm:inline">
          Watchers
        </span>

        {/* Alert badge */}
        {totalAlerts > 0 && (
          <span className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px]
                          flex items-center justify-center px-1
                          bg-enjin-red text-white text-[9px] font-bold
                          rounded-full animate-pulse-glow">
            {totalAlerts > 99 ? '99+' : totalAlerts}
          </span>
        )}
      </button>

      {/* Watcher panel */}
      {active && (
        <div className="absolute top-full right-0 mt-2 w-80 max-h-[480px]
                       glass-panel rounded border border-white/10
                       shadow-2xl shadow-black/60 animate-fade-in
                       flex flex-col overflow-hidden">
          {/* Header */}
          <div className="flex-shrink-0 px-4 pt-4 pb-3 border-b border-white/5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xs font-bold uppercase tracking-[0.15em] text-enjin-blue/80">
                Active Watchers
              </h3>
              <span className="text-[10px] text-white/30 font-mono">
                {watchers.length} total
              </span>
            </div>

            {/* Filter tabs */}
            <div className="flex items-center gap-1">
              {(
                [
                  { value: 'all' as const, label: 'All' },
                  { value: 'active' as const, label: 'Active' },
                  { value: 'alerts' as const, label: `Alerts (${totalAlerts})` },
                ] as const
              ).map((tab) => (
                <button
                  key={tab.value}
                  onClick={() => setFilter(tab.value)}
                  className={`px-2 py-1 text-[10px] font-mono uppercase tracking-wider
                             rounded transition-colors
                             ${
                               filter === tab.value
                                 ? 'bg-enjin-blue/15 text-enjin-blue'
                                 : 'text-white/30 hover:text-white/50'
                             }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          {/* Watcher list */}
          <div className="flex-1 overflow-y-auto">
            {filteredWatchers.length === 0 ? (
              <div className="px-4 py-8 text-center">
                <svg
                  className="w-8 h-8 mx-auto mb-2 text-white/10"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={1}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                  />
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                  />
                </svg>
                <p className="text-xs text-white/20 font-mono">
                  {filter === 'all'
                    ? 'No watchers configured'
                    : `No ${filter} watchers`}
                </p>
              </div>
            ) : (
              filteredWatchers.map((watcher) => (
                <div
                  key={watcher.id}
                  onClick={() => onWatcherSelect(watcher)}
                  className="flex items-start gap-3 px-4 py-3
                            border-b border-white/[0.03] last:border-b-0
                            cursor-pointer hover:bg-white/5 transition-colors group"
                >
                  {/* Status dot */}
                  <div className="flex-shrink-0 mt-1 relative">
                    <div
                      className={`w-2.5 h-2.5 rounded-full
                                 ${TYPE_COLORS[watcher.type] || 'bg-white/30'}
                                 ${watcher.active ? 'flicker' : 'opacity-30'}`}
                    />
                    {watcher.active && (
                      <div
                        className={`absolute inset-0 rounded-full
                                   ${TYPE_COLORS[watcher.type] || 'bg-white/30'}
                                   ripple`}
                      />
                    )}
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-white/80 truncate group-hover:text-white transition-colors">
                        {watcher.name}
                      </span>
                      {!watcher.active && (
                        <span className="text-[9px] text-white/20 uppercase">paused</span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-[10px] text-white/30 uppercase tracking-wider">
                        {watcher.type}
                      </span>
                      <span className="text-[10px] text-white/20">
                        {formatRelativeTime(watcher.last_activity)}
                      </span>
                    </div>
                    {watcher.description && (
                      <p className="text-[11px] text-white/20 mt-1 truncate">
                        {watcher.description}
                      </p>
                    )}
                  </div>

                  {/* Alert count */}
                  <div className="flex-shrink-0 flex items-center gap-2">
                    {(watcher.alert_count ?? 0) > 0 && (
                      <span className="inline-flex items-center justify-center
                                      min-w-[20px] h-5 px-1.5
                                      bg-enjin-red/20 text-enjin-red text-[10px] font-bold
                                      rounded-full border border-enjin-red/30">
                        {watcher.alert_count}
                      </span>
                    )}

                    {/* Remove button */}
                    {onRemoveWatcher && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          onRemoveWatcher(watcher.id)
                        }}
                        className="opacity-0 group-hover:opacity-100
                                  p-1 text-white/20 hover:text-enjin-red
                                  transition-all"
                        aria-label={`Remove watcher ${watcher.name}`}
                      >
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Footer */}
          {watchers.length > 0 && (
            <div className="flex-shrink-0 px-4 py-2 border-t border-white/5
                           flex items-center justify-between">
              <span className="text-[9px] text-white/15 font-mono uppercase tracking-wider">
                Auto-refresh: 30s
              </span>
              <div className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-enjin-green/60 flicker" />
                <span className="text-[9px] text-enjin-green/40 font-mono uppercase">
                  Live
                </span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
