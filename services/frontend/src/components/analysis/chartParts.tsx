'use client'

/**
 * Plumbing shared by the analysis charts (profile and distribution): the
 * measured container width (text keeps its size on narrow screens), the
 * series colours and a hover tooltip.
 *
 * The series colours are a categorical palette (blue, orange, aqua, violet)
 * with a light and a dark step each; light-mode aqua stays below 3:1 on
 * white, so every line also carries a direct label. Text never takes a
 * series colour.
 */

import { useEffect, useRef, useState, type ReactNode } from 'react'

export const FALLBACK_WIDTH = 640

export function useMeasuredWidth<T extends HTMLElement = HTMLDivElement>() {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(0)
  useEffect(() => {
    const node = ref.current
    if (!node) return
    const measure = () => setWidth(node.clientWidth)
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(measure)
    observer.observe(node)
    return () => observer.disconnect()
  }, [])
  return { ref, width: width > 0 ? width : FALLBACK_WIDTH }
}

/** Stroke, fill and swatch classes per series slot, light and dark steps. */
export const SERIES = [
  {
    stroke: 'stroke-[#2a78d6] dark:stroke-[#3987e5]',
    fill: 'fill-[#2a78d6] dark:fill-[#3987e5]',
    swatch: 'bg-[#2a78d6] dark:bg-[#3987e5]',
  },
  {
    stroke: 'stroke-[#eb6834] dark:stroke-[#d95926]',
    fill: 'fill-[#eb6834] dark:fill-[#d95926]',
    swatch: 'bg-[#eb6834] dark:bg-[#d95926]',
  },
  {
    stroke: 'stroke-[#1baf7a] dark:stroke-[#199e70]',
    fill: 'fill-[#1baf7a] dark:fill-[#199e70]',
    swatch: 'bg-[#1baf7a] dark:bg-[#199e70]',
  },
  {
    stroke: 'stroke-[#6250d6] dark:stroke-[#9085e9]',
    fill: 'fill-[#6250d6] dark:fill-[#9085e9]',
    swatch: 'bg-[#6250d6] dark:bg-[#9085e9]',
  },
] as const

/**
 * The colour slot of the i-th series. More than four series share the last
 * slot (the direct labels still tell them apart); callers with many series
 * use small multiples instead of cycling hues.
 */
export function seriesSlot(i: number) {
  return SERIES[Math.min(Math.max(i, 0), SERIES.length - 1)]
}

export const AXIS_TEXT = 'fill-zinc-500 dark:fill-zinc-400'
export const GRID_LINE = 'stroke-zinc-200 dark:stroke-zinc-800'
export const REF_LINE = 'stroke-zinc-500 dark:stroke-zinc-400'
export const BASE_LINE = 'stroke-zinc-300 dark:stroke-zinc-700'

export interface TooltipState {
  x: number
  y: number
  content: ReactNode
}

/** A tooltip positioned inside a relative container, kept on screen. */
export function ChartTooltip({
  tip,
  width,
}: {
  tip: TooltipState | null
  width: number
}) {
  if (!tip) return null
  const left = Math.min(Math.max(tip.x + 12, 4), Math.max(4, width - 220))
  return (
    <div
      className="pointer-events-none absolute z-10 w-max max-w-[210px] rounded-md border border-zinc-200 bg-white px-2.5 py-1.5 text-xs text-zinc-700 shadow-md dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
      style={{ left, top: Math.max(0, tip.y - 8) }}
      role="tooltip"
    >
      {tip.content}
    </div>
  )
}
