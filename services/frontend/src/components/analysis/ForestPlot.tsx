'use client'

/**
 * Forest plot: one row per estimate with its point estimate, its confidence
 * interval (thin line), optionally an inner interval (thick line, e.g. the
 * TOST interval an equivalence decision uses), a dashed reference line at
 * the null value and an optional shaded band (e.g. equivalence bounds).
 *
 * Generic on purpose: the analysis results page feeds it estimates of one
 * contrast across scopes, and overlays (the compliance views) reuse it with
 * their own rows and bands. It draws what it is given and computes nothing
 * statistical.
 *
 * The SVG is drawn at the container's measured width (ResizeObserver), so
 * text keeps its size on narrow screens; long row labels are shortened with
 * the full label in a tooltip.
 */

import { useI18n } from '@/contexts/I18nContext'
import { axisTicks, formatInterval, formatNumber } from '@/lib/analysis/results'
import { useEffect, useRef, useState } from 'react'

export interface ForestPlotInterval {
  lower: number
  upper: number
}

export interface ForestPlotRow {
  id: string
  label: string
  estimate: number | null
  lower: number | null
  upper: number | null
  /** Drawn as a thicker segment inside the interval when given. */
  inner?: ForestPlotInterval | null
  /** Shown in place of the interval text when the row has no estimate. */
  note?: string | null
  /** Visually emphasised (e.g. the pooled estimate). */
  emphasis?: boolean
}

export interface ForestPlotBand extends ForestPlotInterval {
  label?: string
}

export interface ForestPlotProps {
  rows: readonly ForestPlotRow[]
  /** Dashed reference line (usually the contrast's null value). */
  nullValue?: number | null
  /** Shaded region, e.g. equivalence bounds; omitted when null. */
  band?: ForestPlotBand | null
  /** Accessible name of the chart. */
  ariaLabel: string
  /** Label of the axis (e.g. the outcome). */
  axisLabel?: string
  /** Legend entries for the lines; omitted entries are not shown. */
  legend?: { interval?: string; inner?: string; band?: string }
  className?: string
  'data-testid'?: string
}

const ROW_HEIGHT = 30
const AXIS_HEIGHT = 34
const TOP_PAD = 8
const VALUE_WIDTH = 180
const FALLBACK_WIDTH = 720
const CHAR_WIDTH = 6.6

function useMeasuredWidth() {
  const ref = useRef<HTMLDivElement>(null)
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
  return [ref, width] as const
}

function shorten(label: string, maxChars: number): string {
  if (label.length <= maxChars) return label
  return `${label.slice(0, Math.max(1, maxChars - 1))}…`
}

export function ForestPlot({
  rows,
  nullValue = 0,
  band = null,
  ariaLabel,
  axisLabel,
  legend,
  className,
  'data-testid': testId = 'forest-plot',
}: ForestPlotProps) {
  const { locale } = useI18n()
  const [containerRef, measured] = useMeasuredWidth()
  const width = measured > 0 ? measured : FALLBACK_WIDTH
  const compact = width < 560
  const valueWidth = compact ? 0 : VALUE_WIDTH
  const labelWidth = Math.min(240, Math.max(96, Math.round(width * 0.28)))
  const plotLeft = labelWidth + 8
  const plotRight = width - valueWidth - 12
  const plotWidth = Math.max(40, plotRight - plotLeft)
  const height = TOP_PAD + rows.length * ROW_HEIGHT + AXIS_HEIGHT
  const plotBottom = TOP_PAD + rows.length * ROW_HEIGHT

  const domainValues: (number | null | undefined)[] = []
  for (const row of rows) {
    domainValues.push(row.estimate, row.lower, row.upper)
    if (row.inner) domainValues.push(row.inner.lower, row.inner.upper)
  }
  if (nullValue !== null && nullValue !== undefined)
    domainValues.push(nullValue)
  if (band) domainValues.push(band.lower, band.upper)
  const { min, max, ticks } = axisTicks(domainValues)
  const x = (value: number) =>
    plotLeft + ((value - min) / (max - min || 1)) * plotWidth
  const clampX = (value: number) =>
    Math.min(plotLeft + plotWidth, Math.max(plotLeft, x(value)))
  const maxLabelChars = Math.floor(labelWidth / CHAR_WIDTH)

  return (
    <div className={className}>
      <div ref={containerRef} className="w-full">
        <svg
          role="img"
          aria-label={ariaLabel}
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          className="block text-xs"
          data-testid={testId}
        >
          <title>{ariaLabel}</title>
          {rows.map((row, i) =>
            i % 2 === 1 ? (
              <rect
                key={`stripe-${row.id}`}
                x={0}
                y={TOP_PAD + i * ROW_HEIGHT}
                width={width}
                height={ROW_HEIGHT}
                className="fill-zinc-50 dark:fill-zinc-800/40"
              />
            ) : null,
          )}
          {band && (
            <rect
              data-testid="forest-plot-band"
              x={clampX(band.lower)}
              y={TOP_PAD}
              width={Math.max(0, clampX(band.upper) - clampX(band.lower))}
              height={plotBottom - TOP_PAD}
              className="fill-emerald-500/15 dark:fill-emerald-400/15"
            >
              {band.label && <title>{band.label}</title>}
            </rect>
          )}
          {ticks.map((tick) => (
            <g key={`tick-${tick}`}>
              <line
                x1={x(tick)}
                x2={x(tick)}
                y1={TOP_PAD}
                y2={plotBottom}
                className="stroke-zinc-200 dark:stroke-zinc-800"
                strokeWidth={1}
              />
              <text
                x={x(tick)}
                y={plotBottom + 14}
                textAnchor="middle"
                className="fill-zinc-500 dark:fill-zinc-400"
              >
                {formatNumber(tick, locale, 3)}
              </text>
            </g>
          ))}
          {axisLabel && (
            <text
              x={plotLeft + plotWidth / 2}
              y={plotBottom + 29}
              textAnchor="middle"
              className="fill-zinc-600 dark:fill-zinc-300"
            >
              {axisLabel}
            </text>
          )}
          {nullValue !== null &&
            nullValue !== undefined &&
            nullValue >= min &&
            nullValue <= max && (
              <line
                data-testid="forest-plot-null"
                x1={x(nullValue)}
                x2={x(nullValue)}
                y1={TOP_PAD}
                y2={plotBottom}
                strokeDasharray="4 3"
                strokeWidth={1.25}
                className="stroke-zinc-500 dark:stroke-zinc-400"
              />
            )}
          {rows.map((row, i) => {
            const cy = TOP_PAD + i * ROW_HEIGHT + ROW_HEIGHT / 2
            const has =
              typeof row.estimate === 'number' && Number.isFinite(row.estimate)
            const hasInterval =
              typeof row.lower === 'number' &&
              typeof row.upper === 'number' &&
              Number.isFinite(row.lower) &&
              Number.isFinite(row.upper)
            const label = shorten(row.label, maxLabelChars)
            return (
              <g key={row.id} data-testid="forest-plot-row">
                <text
                  x={labelWidth}
                  y={cy + 4}
                  textAnchor="end"
                  className={
                    row.emphasis
                      ? 'fill-zinc-900 font-semibold dark:fill-white'
                      : 'fill-zinc-700 dark:fill-zinc-300'
                  }
                >
                  {label !== row.label && <title>{row.label}</title>}
                  {label}
                </text>
                {hasInterval && (
                  <line
                    x1={clampX(row.lower as number)}
                    x2={clampX(row.upper as number)}
                    y1={cy}
                    y2={cy}
                    strokeWidth={1.5}
                    className="stroke-zinc-700 dark:stroke-zinc-300"
                  />
                )}
                {row.inner && (
                  <line
                    data-testid="forest-plot-inner"
                    x1={clampX(row.inner.lower)}
                    x2={clampX(row.inner.upper)}
                    y1={cy}
                    y2={cy}
                    strokeWidth={4}
                    strokeLinecap="round"
                    className="stroke-emerald-700/70 dark:stroke-emerald-400/70"
                  />
                )}
                {has && (
                  <rect
                    data-testid="forest-plot-point"
                    x={clampX(row.estimate as number) - (row.emphasis ? 5 : 4)}
                    y={cy - (row.emphasis ? 5 : 4)}
                    width={row.emphasis ? 10 : 8}
                    height={row.emphasis ? 10 : 8}
                    className="fill-emerald-600 stroke-white dark:fill-emerald-400 dark:stroke-zinc-900"
                    strokeWidth={1}
                    transform={
                      row.emphasis
                        ? `rotate(45 ${clampX(row.estimate as number)} ${cy})`
                        : undefined
                    }
                  />
                )}
                {!has && (
                  <text
                    x={plotLeft + 4}
                    y={cy + 4}
                    className="fill-zinc-400 italic dark:fill-zinc-500"
                  >
                    {row.note || '—'}
                  </text>
                )}
                {!compact && (
                  <text
                    x={width - 4}
                    y={cy + 4}
                    textAnchor="end"
                    className="fill-zinc-700 font-mono dark:fill-zinc-300"
                  >
                    {has
                      ? `${formatNumber(row.estimate, locale)} ${hasInterval ? formatInterval(row.lower, row.upper, locale) : ''}`.trim()
                      : ''}
                  </text>
                )}
              </g>
            )
          })}
        </svg>
      </div>
      {legend && (legend.interval || legend.inner || (band && legend.band)) && (
        <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-zinc-600 dark:text-zinc-400">
          {legend.interval && (
            <span className="inline-flex items-center gap-2">
              <svg width="22" height="10" aria-hidden="true">
                <line
                  x1="1"
                  x2="21"
                  y1="5"
                  y2="5"
                  strokeWidth={1.5}
                  className="stroke-zinc-700 dark:stroke-zinc-300"
                />
                <rect
                  x="7"
                  y="1"
                  width="8"
                  height="8"
                  className="fill-emerald-600 dark:fill-emerald-400"
                />
              </svg>
              {legend.interval}
            </span>
          )}
          {legend.inner && rows.some((r) => r.inner) && (
            <span className="inline-flex items-center gap-2">
              <svg width="22" height="10" aria-hidden="true">
                <line
                  x1="2"
                  x2="20"
                  y1="5"
                  y2="5"
                  strokeWidth={4}
                  strokeLinecap="round"
                  className="stroke-emerald-700/70 dark:stroke-emerald-400/70"
                />
              </svg>
              {legend.inner}
            </span>
          )}
          {band && legend.band && (
            <span className="inline-flex items-center gap-2">
              <span
                aria-hidden="true"
                className="inline-block h-3 w-5 rounded-sm bg-emerald-500/15 ring-1 ring-emerald-500/30 dark:bg-emerald-400/15"
              />
              {legend.band}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
