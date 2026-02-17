'use client'

/* ------------------------------------------------------------------ */
/*  EntityPanel - Slide-in detail panel for a selected entity          */
/* ------------------------------------------------------------------ */

import { useState, useEffect } from 'react'
import type { Entity, Connection, Event as EnjinEvent, EntityType } from '@/lib/types'
import { getEntityConnections, getEntity } from '@/lib/api'

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface EntityPanelProps {
  entity: Entity | null
  onClose: () => void
  onWatch: (entity: Entity) => void
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

const TYPE_BADGE_CLASSES: Record<EntityType, string> = {
  person: 'badge-person',
  organization: 'badge-org',
  location: 'badge-location',
  vessel: 'badge-event',
  asset: 'badge-alert',
  unknown: 'badge',
}

const TYPE_ICONS: Record<EntityType, string> = {
  person: '\u{1F464}',      // silhouette -- rendered as text fallback
  organization: '\u{1F3E2}',
  location: '\u{1F4CD}',
  vessel: '\u{1F6A2}',
  asset: '\u{1F4BC}',
  unknown: '\u{2753}',
}

function formatDate(dateStr?: string): string {
  if (!dateStr) return '--'
  return new Date(dateStr).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function EntityPanel({
  entity,
  onClose,
  onWatch,
}: EntityPanelProps) {
  const [connections, setConnections] = useState<Connection[]>([])
  const [relatedEvents, setRelatedEvents] = useState<EnjinEvent[]>([])
  const [isLoadingConnections, setIsLoadingConnections] = useState(false)
  const [activeTab, setActiveTab] = useState<'details' | 'connections' | 'events'>('details')

  // Fetch connections when entity changes
  useEffect(() => {
    if (!entity) {
      setConnections([])
      setRelatedEvents([])
      return
    }

    setActiveTab('details')
    setIsLoadingConnections(true)

    getEntityConnections(entity.id, 1)
      .then(setConnections)
      .catch(() => setConnections([]))
      .finally(() => setIsLoadingConnections(false))
  }, [entity?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!entity) return null

  return (
    <div className="fixed top-0 right-0 h-full w-full sm:w-[420px] z-40 animate-slide-in-right">
      {/* Backdrop for mobile */}
      <div
        className="absolute inset-0 bg-black/50 sm:hidden"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="absolute top-0 right-0 h-full w-full sm:w-[420px] glass-panel border-l border-white/5 flex flex-col overflow-hidden">
        {/* ---- Header ---- */}
        <div className="flex-shrink-0 px-5 pt-5 pb-4 border-b border-white/5">
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1.5">
                <span className={TYPE_BADGE_CLASSES[entity.type] || 'badge'}>
                  {entity.type}
                </span>
                {entity.nationality && (
                  <span className="text-[10px] text-white/40 uppercase tracking-wider">
                    {entity.nationality}
                  </span>
                )}
              </div>
              <h2 className="text-lg font-bold text-white truncate text-glow-blue">
                {entity.name}
              </h2>
              {entity.role && (
                <p className="text-sm text-white/50 mt-0.5">{entity.role}</p>
              )}
            </div>

            {/* Close button */}
            <button
              onClick={onClose}
              className="flex-shrink-0 w-8 h-8 flex items-center justify-center
                         rounded border border-white/10 text-white/40
                         hover:text-white hover:border-white/30
                         transition-colors"
              aria-label="Close panel"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2 mt-3">
            <button
              onClick={() => onWatch(entity)}
              className="btn-cyber-success text-xs flex items-center gap-1.5"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              </svg>
              Watch
            </button>
            <button className="btn-cyber text-xs flex items-center gap-1.5">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
              </svg>
              Ripple
            </button>
          </div>
        </div>

        {/* ---- Tab bar ---- */}
        <div className="flex-shrink-0 flex border-b border-white/5">
          {(['details', 'connections', 'events'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`flex-1 px-4 py-2.5 text-xs font-mono uppercase tracking-wider
                         transition-colors border-b-2
                         ${
                           activeTab === tab
                             ? 'text-enjin-blue border-enjin-blue bg-enjin-blue/5'
                             : 'text-white/40 border-transparent hover:text-white/60 hover:bg-white/2'
                         }`}
            >
              {tab}
              {tab === 'connections' && connections.length > 0 && (
                <span className="ml-1.5 text-[10px] text-enjin-blue/60">
                  {connections.length}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* ---- Tab content ---- */}
        <div className="flex-1 overflow-y-auto">
          {/* Details Tab */}
          {activeTab === 'details' && (
            <div className="p-5 space-y-5 animate-fade-in">
              {/* Description */}
              {entity.description && (
                <div>
                  <SectionLabel>Description</SectionLabel>
                  <p className="text-sm text-white/70 leading-relaxed">
                    {entity.description}
                  </p>
                </div>
              )}

              {/* Key facts */}
              <div>
                <SectionLabel>Key Facts</SectionLabel>
                <div className="grid grid-cols-2 gap-2">
                  <FactCard label="Type" value={entity.type} />
                  <FactCard label="Role" value={entity.role} />
                  <FactCard label="Nationality" value={entity.nationality} />
                  <FactCard label="Country" value={entity.country} />
                  {entity.org_type && (
                    <FactCard label="Org Type" value={entity.org_type} />
                  )}
                  {entity.latitude != null && (
                    <FactCard
                      label="Coordinates"
                      value={`${entity.latitude.toFixed(2)}, ${entity.longitude?.toFixed(2)}`}
                    />
                  )}
                </div>
              </div>

              {/* Aliases */}
              {entity.aliases && entity.aliases.length > 0 && (
                <div>
                  <SectionLabel>Known Aliases</SectionLabel>
                  <div className="flex flex-wrap gap-1.5">
                    {entity.aliases.map((alias) => (
                      <span
                        key={alias}
                        className="px-2 py-1 text-xs bg-white/5 border border-white/10
                                   rounded text-white/60 font-mono"
                      >
                        {alias}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Metadata */}
              {Object.keys(entity.metadata).length > 0 && (
                <div>
                  <SectionLabel>Metadata</SectionLabel>
                  <div className="space-y-1">
                    {Object.entries(entity.metadata).map(([key, value]) => (
                      <div
                        key={key}
                        className="flex items-start gap-2 text-xs"
                      >
                        <span className="text-white/30 uppercase tracking-wider min-w-[80px] flex-shrink-0">
                          {key}
                        </span>
                        <span className="text-white/60 break-all">
                          {String(value)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Connections Tab */}
          {activeTab === 'connections' && (
            <div className="p-5 animate-fade-in">
              {isLoadingConnections ? (
                <LoadingState label="Loading connections..." />
              ) : connections.length === 0 ? (
                <EmptyState label="No connections found" />
              ) : (
                <div className="space-y-2">
                  {connections.map((conn, idx) => (
                    <div
                      key={conn.id ?? idx}
                      className="glass-panel-hover rounded p-3 cursor-pointer"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 min-w-0">
                          <div className="w-2 h-2 rounded-full bg-enjin-purple flex-shrink-0" />
                          <span className="text-sm text-white/80 truncate">
                            {conn.label ?? conn.to_id}
                          </span>
                        </div>
                        <span className="badge text-[10px] bg-white/5 text-white/40 border border-white/10 flex-shrink-0 ml-2">
                          {conn.type.replace('_', ' ')}
                        </span>
                      </div>
                      {conn.metadata && Object.keys(conn.metadata).length > 0 && (
                        <div className="mt-1.5 text-[10px] text-white/30 truncate pl-4">
                          {Object.entries(conn.metadata)
                            .slice(0, 2)
                            .map(([k, v]) => `${k}: ${v}`)
                            .join(' | ')}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Events Tab */}
          {activeTab === 'events' && (
            <div className="p-5 animate-fade-in">
              {relatedEvents.length === 0 ? (
                <EmptyState label="No recent events" />
              ) : (
                <div className="space-y-2">
                  {relatedEvents.map((event) => (
                    <div
                      key={event.id}
                      className="glass-panel-hover rounded p-3 cursor-pointer"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-sm text-white/80 truncate">
                            {event.title}
                          </p>
                          {event.summary && (
                            <p className="text-xs text-white/40 mt-1 line-clamp-2">
                              {event.summary}
                            </p>
                          )}
                        </div>
                        {event.category && (
                          <span className="badge-event text-[10px] flex-shrink-0">
                            {event.category}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 mt-2 text-[10px] text-white/30">
                        {event.occurred_at && (
                          <span>{formatDate(event.occurred_at)}</span>
                        )}
                        {event.location_name && (
                          <span className="truncate">{event.location_name}</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ---- Footer ---- */}
        <div className="flex-shrink-0 px-5 py-3 border-t border-white/5 flex items-center justify-between">
          <span className="text-[10px] text-white/20 font-mono uppercase tracking-wider">
            Entity ID: {entity.id.slice(0, 8)}...
          </span>
          <span className="text-[10px] text-white/20 font-mono">
            {formatDate(entity.updated_at ?? entity.created_at)}
          </span>
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-[10px] uppercase tracking-[0.15em] text-enjin-blue/60 font-bold mb-2">
      {children}
    </h3>
  )
}

function FactCard({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="bg-white/[0.02] border border-white/5 rounded px-3 py-2">
      <div className="text-[10px] text-white/30 uppercase tracking-wider mb-0.5">
        {label}
      </div>
      <div className="text-sm text-white/70 truncate">
        {value || '--'}
      </div>
    </div>
  )
}

function LoadingState({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-white/30">
      <div className="w-8 h-8 border-2 border-enjin-blue/20 border-t-enjin-blue rounded-full animate-spin mb-3" />
      <span className="text-xs font-mono">{label}</span>
    </div>
  )
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-white/20">
      <svg className="w-10 h-10 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
      </svg>
      <span className="text-xs font-mono">{label}</span>
    </div>
  )
}
