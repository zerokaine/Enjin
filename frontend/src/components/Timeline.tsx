'use client'

/* ------------------------------------------------------------------ */
/*  Timeline - Bottom bar timeline scrubber with playback controls     */
/* ------------------------------------------------------------------ */

import { useState, useRef, useCallback, useEffect, useMemo } from 'react'
import type { TimeRange } from '@/lib/types'

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface TimelineProps {
  range: TimeRange
  currentPosition: number // 0-1 normalized position
  onPositionChange: (position: number) => void
  eventDensity: number[]
  onPlaybackChange?: (playing: boolean, speed: number) => void
  onRangeChange?: (range: TimeRange) => void
}

type PlaybackSpeed = 0.5 | 1 | 2 | 4

const SPEEDS: PlaybackSpeed[] = [0.5, 1, 2, 4]

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function formatDateShort(date: Date): string {
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: '2-digit',
  })
}

function formatDateTime(date: Date): string {
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function lerp(start: number, end: number, t: number): number {
  return start + (end - start) * Math.max(0, Math.min(1, t))
}

function positionToDate(range: TimeRange, position: number): Date {
  const startMs = range.start.getTime()
  const endMs = range.end.getTime()
  return new Date(lerp(startMs, endMs, position))
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function Timeline({
  range,
  currentPosition,
  onPositionChange,
  eventDensity,
  onPlaybackChange,
  onRangeChange,
}: TimelineProps) {
  const [isPlaying, setIsPlaying] = useState(false)
  const [speed, setSpeed] = useState<PlaybackSpeed>(1)
  const [isDragging, setIsDragging] = useState(false)
  const [isExpanded, setIsExpanded] = useState(true)
  const trackRef = useRef<HTMLDivElement>(null)
  const playIntervalRef = useRef<NodeJS.Timeout | null>(null)

  // Current date based on position
  const currentDate = useMemo(
    () => positionToDate(range, currentPosition),
    [range, currentPosition],
  )

  // Normalize density data for bar heights
  const maxDensity = useMemo(
    () => Math.max(1, ...eventDensity),
    [eventDensity],
  )

  /* ---------------------------------------------------------------- */
  /*  Playback engine                                                  */
  /* ---------------------------------------------------------------- */

  useEffect(() => {
    if (isPlaying) {
      const interval = 50 // ms per tick
      const step = (speed * 0.001) // position increment per tick

      playIntervalRef.current = setInterval(() => {
        onPositionChange(Math.min(1, currentPosition + step))
      }, interval)
    }

    return () => {
      if (playIntervalRef.current) {
        clearInterval(playIntervalRef.current)
        playIntervalRef.current = null
      }
    }
  }, [isPlaying, speed, currentPosition, onPositionChange])

  // Auto-pause at end
  useEffect(() => {
    if (currentPosition >= 1 && isPlaying) {
      setIsPlaying(false)
      onPlaybackChange?.(false, speed)
    }
  }, [currentPosition, isPlaying, speed, onPlaybackChange])

  /* ---------------------------------------------------------------- */
  /*  Scrub handlers                                                   */
  /* ---------------------------------------------------------------- */

  const handleTrackInteraction = useCallback(
    (clientX: number) => {
      if (!trackRef.current) return
      const rect = trackRef.current.getBoundingClientRect()
      const x = clientX - rect.left
      const normalized = Math.max(0, Math.min(1, x / rect.width))
      onPositionChange(normalized)
    },
    [onPositionChange],
  )

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      setIsDragging(true)
      handleTrackInteraction(e.clientX)
    },
    [handleTrackInteraction],
  )

  useEffect(() => {
    if (!isDragging) return

    function handleMouseMove(e: MouseEvent) {
      handleTrackInteraction(e.clientX)
    }

    function handleMouseUp() {
      setIsDragging(false)
    }

    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isDragging, handleTrackInteraction])

  /* ---------------------------------------------------------------- */
  /*  Playback controls                                                */
  /* ---------------------------------------------------------------- */

  const togglePlay = useCallback(() => {
    const next = !isPlaying
    // Reset to start if at end
    if (next && currentPosition >= 1) {
      onPositionChange(0)
    }
    setIsPlaying(next)
    onPlaybackChange?.(next, speed)
  }, [isPlaying, currentPosition, speed, onPositionChange, onPlaybackChange])

  const cycleSpeed = useCallback(() => {
    const idx = SPEEDS.indexOf(speed)
    const nextSpeed = SPEEDS[(idx + 1) % SPEEDS.length]
    setSpeed(nextSpeed)
    if (isPlaying) {
      onPlaybackChange?.(true, nextSpeed)
    }
  }, [speed, isPlaying, onPlaybackChange])

  const skipToStart = useCallback(() => {
    onPositionChange(0)
  }, [onPositionChange])

  const skipToEnd = useCallback(() => {
    onPositionChange(1)
    setIsPlaying(false)
  }, [onPositionChange])

  /* ---------------------------------------------------------------- */
  /*  Render                                                           */
  /* ---------------------------------------------------------------- */

  if (!isExpanded) {
    return (
      <div className="fixed bottom-0 left-0 right-0 z-30">
        <button
          onClick={() => setIsExpanded(true)}
          className="mx-auto flex items-center gap-2 px-4 py-1.5
                     glass-panel rounded-t border-b-0
                     text-xs text-white/40 hover:text-white/60 transition-colors"
        >
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 15l7-7 7 7" />
          </svg>
          Timeline
        </button>
      </div>
    )
  }

  return (
    <div className="fixed bottom-0 left-0 right-0 z-30 animate-slide-up">
      <div className="glass-panel border-t border-white/5">
        {/* Collapse button */}
        <button
          onClick={() => setIsExpanded(false)}
          className="absolute -top-6 left-1/2 -translate-x-1/2
                     flex items-center gap-2 px-3 py-1
                     glass-panel rounded-t border-b-0
                     text-[10px] text-white/30 hover:text-white/50 transition-colors"
        >
          <svg className="w-2.5 h-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        <div className="px-4 py-3">
          {/* Top row: current date + range */}
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] text-white/30 font-mono uppercase tracking-wider">
              {formatDateShort(range.start)}
            </span>
            <span className="text-xs text-enjin-blue font-mono font-bold text-glow-blue">
              {formatDateTime(currentDate)}
            </span>
            <span className="text-[10px] text-white/30 font-mono uppercase tracking-wider">
              {formatDateShort(range.end)}
            </span>
          </div>

          {/* Event density bars + scrubber */}
          <div className="relative mb-3">
            {/* Density bars */}
            <div className="flex items-end gap-px h-8 mb-1">
              {eventDensity.map((count, idx) => {
                const height = (count / maxDensity) * 100
                const isAtPosition =
                  Math.abs(idx / eventDensity.length - currentPosition) <
                  1 / eventDensity.length

                return (
                  <div
                    key={idx}
                    className="flex-1 min-w-[2px] rounded-t transition-all duration-150"
                    style={{
                      height: `${Math.max(2, height)}%`,
                      backgroundColor: isAtPosition
                        ? 'rgb(0, 212, 255)'
                        : count > 0
                          ? `rgba(0, 212, 255, ${0.15 + (height / 100) * 0.4})`
                          : 'rgba(255, 255, 255, 0.03)',
                    }}
                  />
                )
              })}
            </div>

            {/* Scrubber track */}
            <div
              ref={trackRef}
              className="relative h-2 bg-white/5 rounded-full cursor-pointer group"
              onMouseDown={handleMouseDown}
            >
              {/* Filled portion */}
              <div
                className="absolute top-0 left-0 h-full bg-gradient-to-r from-enjin-blue/60 to-enjin-purple/60 rounded-full"
                style={{ width: `${currentPosition * 100}%` }}
              />

              {/* Playhead */}
              <div
                className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2
                           w-3.5 h-3.5 rounded-full bg-enjin-blue border-2 border-enjin-dark
                           shadow-lg shadow-enjin-blue/30
                           group-hover:scale-125 transition-transform"
                style={{ left: `${currentPosition * 100}%` }}
              />
            </div>
          </div>

          {/* Playback controls */}
          <div className="flex items-center justify-center gap-3">
            {/* Skip to start */}
            <button
              onClick={skipToStart}
              className="p-1.5 text-white/30 hover:text-white/60 transition-colors"
              aria-label="Skip to start"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
              </svg>
            </button>

            {/* Play / Pause */}
            <button
              onClick={togglePlay}
              className={`w-9 h-9 rounded-full flex items-center justify-center
                         border transition-all
                         ${
                           isPlaying
                             ? 'border-enjin-blue bg-enjin-blue/20 text-enjin-blue glow-blue'
                             : 'border-white/20 bg-white/5 text-white/60 hover:border-white/40 hover:text-white'
                         }`}
              aria-label={isPlaying ? 'Pause' : 'Play'}
            >
              {isPlaying ? (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M10 9v6m4-6v6" />
                </svg>
              ) : (
                <svg className="w-4 h-4 ml-0.5" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M8 5v14l11-7z" />
                </svg>
              )}
            </button>

            {/* Skip to end */}
            <button
              onClick={skipToEnd}
              className="p-1.5 text-white/30 hover:text-white/60 transition-colors"
              aria-label="Skip to end"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
              </svg>
            </button>

            {/* Speed control */}
            <button
              onClick={cycleSpeed}
              className="ml-2 px-2 py-1 text-[10px] font-mono text-white/40
                         border border-white/10 rounded
                         hover:text-white/60 hover:border-white/20 transition-colors"
              aria-label={`Speed: ${speed}x`}
            >
              {speed}x
            </button>

            {/* Event count */}
            <div className="ml-auto text-[10px] text-white/20 font-mono">
              {eventDensity.reduce((a, b) => a + b, 0)} events
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
