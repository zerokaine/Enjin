'use client'

/* ------------------------------------------------------------------ */
/*  SearchBar - Search input with category filters and results list    */
/* ------------------------------------------------------------------ */

import {
  useState,
  useRef,
  useCallback,
  useEffect,
  type KeyboardEvent,
} from 'react'
import useSWR from 'swr'
import { fetcher } from '@/lib/api'
import type { SearchResult, Entity, Event as EnjinEvent, EntityType } from '@/lib/types'

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface SearchBarProps {
  onSelect: (result: SearchResult) => void
}

type CategoryFilter = 'all' | 'person' | 'organization' | 'event' | 'location'

const CATEGORIES: { value: CategoryFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'person', label: 'People' },
  { value: 'organization', label: 'Orgs' },
  { value: 'event', label: 'Events' },
  { value: 'location', label: 'Places' },
]

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function useDebounce<T>(value: T, delayMs: number): T {
  const [debouncedValue, setDebouncedValue] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])

  return debouncedValue
}

function getResultName(result: SearchResult): string {
  if (result.type === 'entity') {
    return (result.item as Entity).name
  }
  return (result.item as EnjinEvent).title
}

function getResultSubtext(result: SearchResult): string {
  if (result.type === 'entity') {
    const entity = result.item as Entity
    return [entity.type, entity.role, entity.nationality]
      .filter(Boolean)
      .join(' \u00B7 ')
  }
  const event = result.item as EnjinEvent
  return [event.category, event.location_name]
    .filter(Boolean)
    .join(' \u00B7 ')
}

function getResultBadgeClass(result: SearchResult): string {
  if (result.type === 'event') return 'badge-event'
  const entity = result.item as Entity
  switch (entity.type) {
    case 'person':
      return 'badge-person'
    case 'organization':
      return 'badge-org'
    case 'location':
      return 'badge-location'
    default:
      return 'badge'
  }
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function SearchBar({ onSelect }: SearchBarProps) {
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState<CategoryFilter>('all')
  const [isFocused, setIsFocused] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(-1)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  const debouncedQuery = useDebounce(query.trim(), 300)

  // Build SWR key
  const searchKey =
    debouncedQuery.length >= 2
      ? `/search?q=${encodeURIComponent(debouncedQuery)}${
          category !== 'all' ? `&type=${category}` : ''
        }&limit=15`
      : null

  const { data: results, isLoading } = useSWR<SearchResult[]>(
    searchKey,
    fetcher,
    {
      revalidateOnFocus: false,
      dedupingInterval: 1_000,
      keepPreviousData: true,
    },
  )

  const showDropdown =
    isFocused && debouncedQuery.length >= 2 && (isLoading || (results && results.length > 0))

  /* ---------------------------------------------------------------- */
  /*  Keyboard navigation                                              */
  /* ---------------------------------------------------------------- */

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (!results || results.length === 0) return

      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault()
          setHighlightedIndex((prev) =>
            prev < results.length - 1 ? prev + 1 : 0,
          )
          break

        case 'ArrowUp':
          e.preventDefault()
          setHighlightedIndex((prev) =>
            prev > 0 ? prev - 1 : results.length - 1,
          )
          break

        case 'Enter':
          e.preventDefault()
          if (highlightedIndex >= 0 && results[highlightedIndex]) {
            selectResult(results[highlightedIndex])
          }
          break

        case 'Escape':
          e.preventDefault()
          inputRef.current?.blur()
          setIsFocused(false)
          break
      }
    },
    [results, highlightedIndex], // eslint-disable-line react-hooks/exhaustive-deps
  )

  // Reset highlight when results change
  useEffect(() => {
    setHighlightedIndex(-1)
  }, [results])

  // Scroll highlighted item into view
  useEffect(() => {
    if (highlightedIndex < 0 || !listRef.current) return
    const items = listRef.current.querySelectorAll('[data-result-item]')
    items[highlightedIndex]?.scrollIntoView({ block: 'nearest' })
  }, [highlightedIndex])

  /* ---------------------------------------------------------------- */
  /*  Selection handler                                                */
  /* ---------------------------------------------------------------- */

  const selectResult = useCallback(
    (result: SearchResult) => {
      onSelect(result)
      setQuery('')
      setIsFocused(false)
      inputRef.current?.blur()
    },
    [onSelect],
  )

  /* ---------------------------------------------------------------- */
  /*  Render                                                           */
  /* ---------------------------------------------------------------- */

  return (
    <div className="relative">
      {/* Search input */}
      <div
        className={`relative flex items-center transition-all duration-200 ${
          isFocused ? 'glow-blue' : ''
        }`}
      >
        {/* Search icon */}
        <div className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30 pointer-events-none">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>

        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setIsFocused(true)}
          onBlur={() => {
            // Delay to allow click on results
            setTimeout(() => setIsFocused(false), 200)
          }}
          onKeyDown={handleKeyDown}
          placeholder="Search entities, events..."
          className="input-cyber pl-10 pr-4 rounded"
          autoComplete="off"
          spellCheck={false}
        />

        {/* Loading spinner */}
        {isLoading && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2">
            <div className="w-4 h-4 border-2 border-enjin-blue/20 border-t-enjin-blue rounded-full animate-spin" />
          </div>
        )}

        {/* Clear button */}
        {query && !isLoading && (
          <button
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => {
              setQuery('')
              inputRef.current?.focus()
            }}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>

      {/* Category filter chips */}
      <div className="flex items-center gap-1.5 mt-2 overflow-x-auto pb-1">
        {CATEGORIES.map((cat) => (
          <button
            key={cat.value}
            onClick={() => setCategory(cat.value)}
            className={`flex-shrink-0 px-2.5 py-1 text-[10px] font-mono uppercase tracking-wider
                       rounded border transition-all duration-150
                       ${
                         category === cat.value
                           ? 'bg-enjin-blue/15 text-enjin-blue border-enjin-blue/40'
                           : 'bg-white/[0.02] text-white/30 border-white/5 hover:text-white/50 hover:border-white/10'
                       }`}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* Results dropdown */}
      {showDropdown && (
        <div
          ref={listRef}
          className="absolute top-full left-0 right-0 mt-1 max-h-[360px] overflow-y-auto
                     glass-panel rounded border border-white/10 shadow-2xl shadow-black/50
                     animate-fade-in z-50"
        >
          {isLoading && (!results || results.length === 0) ? (
            <div className="px-4 py-6 text-center">
              <div className="w-5 h-5 border-2 border-enjin-blue/20 border-t-enjin-blue rounded-full animate-spin mx-auto mb-2" />
              <span className="text-xs text-white/30 font-mono">Searching...</span>
            </div>
          ) : (
            results?.map((result, idx) => (
              <div
                key={result.item.id}
                data-result-item
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => selectResult(result)}
                onMouseEnter={() => setHighlightedIndex(idx)}
                className={`flex items-start gap-3 px-4 py-3 cursor-pointer
                           border-b border-white/5 last:border-b-0
                           transition-colors duration-100
                           ${
                             highlightedIndex === idx
                               ? 'bg-enjin-blue/10'
                               : 'hover:bg-white/5'
                           }`}
              >
                {/* Icon */}
                <div
                  className={`flex-shrink-0 w-8 h-8 rounded flex items-center justify-center
                             ${
                               result.type === 'event'
                                 ? 'bg-enjin-amber/10 text-enjin-amber'
                                 : 'bg-enjin-blue/10 text-enjin-blue'
                             }`}
                >
                  {result.type === 'event' ? (
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                  ) : (
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                    </svg>
                  )}
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-white/80 truncate">
                      {getResultName(result)}
                    </span>
                    <span className={`${getResultBadgeClass(result)} text-[9px] flex-shrink-0`}>
                      {result.type}
                    </span>
                  </div>
                  <p className="text-[11px] text-white/35 truncate mt-0.5">
                    {getResultSubtext(result)}
                  </p>
                </div>

                {/* Score indicator */}
                {result.score != null && (
                  <div className="flex-shrink-0 text-[9px] text-white/20 font-mono">
                    {(result.score * 100).toFixed(0)}%
                  </div>
                )}
              </div>
            ))
          )}

          {/* No results */}
          {!isLoading && results && results.length === 0 && debouncedQuery.length >= 2 && (
            <div className="px-4 py-6 text-center text-xs text-white/30 font-mono">
              No results for &quot;{debouncedQuery}&quot;
            </div>
          )}
        </div>
      )}
    </div>
  )
}
