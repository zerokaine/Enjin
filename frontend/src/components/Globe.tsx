'use client'

/* ------------------------------------------------------------------ */
/*  Globe - 3D globe visualization using globe.gl                      */
/* ------------------------------------------------------------------ */

import { useEffect, useRef, useCallback, useState } from 'react'
import type { GlobePoint, GlobeArc } from '@/lib/types'

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface GlobeProps {
  events: GlobePoint[]
  connections: GlobeArc[]
  onPointClick?: (point: GlobePoint) => void
  onGlobeReady?: () => void
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const GLOBE_IMAGE_URL =
  '//unpkg.com/three-globe/example/img/earth-dark.jpg'
const BUMP_IMAGE_URL =
  '//unpkg.com/three-globe/example/img/earth-topology.png'

/** Auto-rotation speed in degrees per frame */
const AUTO_ROTATE_SPEED = 0.15

/** Colors */
const ATMOSPHERE_COLOR = 'rgba(0, 212, 255, 0.15)'
const ARC_DASH_LENGTH = 0.4
const ARC_DASH_GAP = 0.2
const ARC_DASH_ANIMATE_TIME = 1500

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function Globe({
  events,
  connections,
  onPointClick,
  onGlobeReady,
}: GlobeProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const globeRef = useRef<any>(null)
  const frameRef = useRef<number>(0)
  const isInteracting = useRef(false)
  const [isLoaded, setIsLoaded] = useState(false)

  /* ---------------------------------------------------------------- */
  /*  Initialize globe                                                 */
  /* ---------------------------------------------------------------- */

  const initGlobe = useCallback(async () => {
    if (!containerRef.current) return

    // Dynamic import since globe.gl needs window/document
    const GlobeGL = (await import('globe.gl')).default

    const width = containerRef.current.clientWidth
    const height = containerRef.current.clientHeight

    const globe = new GlobeGL(containerRef.current)
      .width(width)
      .height(height)
      .backgroundColor('rgba(0,0,0,0)')
      .globeImageUrl(GLOBE_IMAGE_URL)
      .bumpImageUrl(BUMP_IMAGE_URL)
      .atmosphereColor(ATMOSPHERE_COLOR)
      .atmosphereAltitude(0.25)
      .showGraticules(true)

      // --- Points layer (events) ---
      .pointsData(events)
      .pointLat((d: object) => (d as GlobePoint).lat)
      .pointLng((d: object) => (d as GlobePoint).lng)
      .pointAltitude((d: object) => (d as GlobePoint).altitude ?? 0.01)
      .pointRadius((d: object) => (d as GlobePoint).size)
      .pointColor((d: object) => (d as GlobePoint).color)
      .pointLabel((d: object) => {
        const p = d as GlobePoint
        return `
          <div class="glass-panel px-3 py-2 rounded text-xs font-mono max-w-[200px]">
            <div class="text-enjin-blue font-bold">${p.label}</div>
            ${p.category ? `<div class="text-white/50 mt-0.5 uppercase text-[10px]">${p.category}</div>` : ''}
          </div>
        `
      })
      .pointsMerge(false)
      .onPointClick((point: object) => {
        onPointClick?.(point as GlobePoint)
      })

      // --- Arcs layer (connections) ---
      .arcsData(connections)
      .arcStartLat((d: object) => (d as GlobeArc).startLat)
      .arcStartLng((d: object) => (d as GlobeArc).startLng)
      .arcEndLat((d: object) => (d as GlobeArc).endLat)
      .arcEndLng((d: object) => (d as GlobeArc).endLng)
      .arcColor((d: object) => {
        const arc = d as GlobeArc
        return [arc.color, `${arc.color}44`]
      })
      .arcStroke((d: object) => (d as GlobeArc).stroke ?? 0.5)
      .arcDashLength(ARC_DASH_LENGTH)
      .arcDashGap(ARC_DASH_GAP)
      .arcDashAnimateTime(ARC_DASH_ANIMATE_TIME)
      .arcLabel((d: object) => {
        const a = d as GlobeArc
        return a.label
          ? `<div class="glass-panel px-2 py-1 rounded text-[10px] font-mono text-white/70">${a.label}</div>`
          : ''
      })

    // Customize Three.js scene
    const scene = globe.scene()
    if (scene) {
      // Dim ambient lighting for darker feel
      scene.children.forEach((child: { type?: string; intensity?: number }) => {
        if (child.type === 'AmbientLight') {
          child.intensity = 0.6
        }
        if (child.type === 'DirectionalLight') {
          child.intensity = 0.4
        }
      })
    }

    // Set initial camera position
    globe.pointOfView({ lat: 20, lng: 0, altitude: 2.5 }, 0)

    // Track interaction state for auto-rotate
    const controls = globe.controls()
    if (controls) {
      controls.addEventListener('start', () => {
        isInteracting.current = true
      })
      controls.addEventListener('end', () => {
        // Resume auto-rotate after 3 seconds of no interaction
        setTimeout(() => {
          isInteracting.current = false
        }, 3000)
      })
      controls.enableDamping = true
      controls.dampingFactor = 0.1
      controls.rotateSpeed = 0.5
      controls.zoomSpeed = 0.8
      controls.minDistance = 120
      controls.maxDistance = 500
    }

    globeRef.current = globe
    setIsLoaded(true)
    onGlobeReady?.()

    // Auto-rotate animation loop
    function animate() {
      if (!isInteracting.current && globeRef.current) {
        const pov = globeRef.current.pointOfView()
        globeRef.current.pointOfView(
          { lat: pov.lat, lng: pov.lng + AUTO_ROTATE_SPEED, altitude: pov.altitude },
          0,
        )
      }
      frameRef.current = requestAnimationFrame(animate)
    }
    frameRef.current = requestAnimationFrame(animate)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  /* ---------------------------------------------------------------- */
  /*  Lifecycle                                                        */
  /* ---------------------------------------------------------------- */

  useEffect(() => {
    initGlobe()

    return () => {
      if (frameRef.current) {
        cancelAnimationFrame(frameRef.current)
      }
      if (globeRef.current) {
        // Clean up the renderer
        globeRef.current._destructor?.()
      }
    }
  }, [initGlobe])

  // Update data when props change
  useEffect(() => {
    if (!globeRef.current) return
    globeRef.current.pointsData(events)
  }, [events])

  useEffect(() => {
    if (!globeRef.current) return
    globeRef.current.arcsData(connections)
  }, [connections])

  // Handle resize
  useEffect(() => {
    function handleResize() {
      if (!containerRef.current || !globeRef.current) return
      globeRef.current
        .width(containerRef.current.clientWidth)
        .height(containerRef.current.clientHeight)
    }

    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  /* ---------------------------------------------------------------- */
  /*  Render                                                           */
  /* ---------------------------------------------------------------- */

  return (
    <div className="relative w-full h-full">
      {/* Globe container */}
      <div
        ref={containerRef}
        className="w-full h-full"
        style={{ cursor: 'grab' }}
      />

      {/* Loading overlay */}
      {!isLoaded && (
        <div className="absolute inset-0 flex items-center justify-center bg-enjin-dark/80 z-10">
          <div className="flex flex-col items-center gap-4">
            <div className="relative w-16 h-16">
              <div className="absolute inset-0 rounded-full border-2 border-enjin-blue/20" />
              <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-enjin-blue animate-spin" />
            </div>
            <span className="text-enjin-blue/70 text-sm font-mono tracking-wider uppercase">
              Initializing Globe
            </span>
          </div>
        </div>
      )}

      {/* Bottom-left: coordinate display */}
      <div className="absolute bottom-4 left-4 text-[10px] font-mono text-white/20 pointer-events-none select-none">
        ENJIN GLOBE v0.1 // LIVE
      </div>
    </div>
  )
}
