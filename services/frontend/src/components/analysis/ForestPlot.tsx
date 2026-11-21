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
 * With `mode="bar"` each estimate is drawn as a bar from 0 instead of a
 * point, with the interval as a whisker and the null value still dashed:
 * the bar view of the evaluations page uses it.
 *
 * The SVG is drawn at the container's measured width (ResizeObserver), so
 * text keeps its size on narrow screens. The label column is as wide as the
 * longest row label, measured in the chart's font. When that label needs
 * more than a share of the width, every label goes on its own line above
 * its row, across the full width; a label longer than even that line is
 * shortened in the middle with the full label in a tooltip. No label is
 * ever cut off at the edge.
 */

import { useI18n } from '@/contexts/I18nContext'
import { axisTicks, formatInterval, formatNumber } from '@/lib/analysis/results'
import { useEffect, useMemo, useRef, useState, type RefObject } from 'react'

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
  /** `point` (default): a marker per estimate; `bar`: a bar from 0, the null value dashed. */
  mode?: 'point' | 'bar'
  className?: string
  'data-testid'?: string
}

const ROW_HEIGHT = 30
/** Row height with the label on its own line above the interval. */
const STACKED_ROW_HEIGHT = 44
/** Baseline of a stacked label and centre of its marks, from the row top. */
const STACKED_LABEL_BASELINE = 14
const STACKED_MARK_Y = 31
/** Top of the marks of a stacked row (grid lines start below the label). */
const STACKED_MARK_TOP = 20
const AXIS_HEIGHT = 34
const TOP_PAD = 8
/** Space between the SVG's left edge and the labels. */
const EDGE = 4
/** Space between the label column and the plot. */
const LABEL_GAP = 8
const MIN_LABEL_WIDTH = 48
/** The label column takes at most this share of the width and this many pixels. */
const MAX_LABEL_SHARE = 0.4
const MAX_LABEL_WIDTH = 360
/** The plot keeps at least this width next to a side label column. */
const MIN_PLOT_WIDTH = 120
/** Font size of the SVG's `text-xs` until it is read from the page. */
const DEFAULT_FONT_SIZE = 13
/**
 * Width of one label character, in ems, when the font cannot be measured
 * (server render, test environment): above the average of a sans-serif
 * font, so the estimate errs towards more room.
 */
const FALLBACK_CHAR_EM = 0.6
const FALLBACK_BOLD_CHAR_EM = 0.64
/** Bounds of the value column, sized to its longest text. */
const MIN_VALUE_WIDTH = 140
const MAX_VALUE_WIDTH = 300
/** Width of one character of the value column (12 px monospace, measured 7.8). */
const MONO_CHAR_WIDTH = 8
/** Gap between the plot and the value column's longest text. */
const VALUE_GAP = 8
const FALLBACK_WIDTH = 720

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

/** Width of a label in pixels; `bold` for emphasised rows. */
export type MeasureText = (text: string, bold: boolean) => number

let measuringContext: OffscreenCanvasRenderingContext2D | null | undefined

function measuringContext2d(): OffscreenCanvasRenderingContext2D | null {
  if (measuringContext === undefined) {
    measuringContext =
      typeof OffscreenCanvas === 'undefined'
        ? null
        : new OffscreenCanvas(1, 1).getContext('2d')
  }
  return measuringContext
}

interface ChartFont {
  family: string
  size: number
}

/**
 * Measures label text in the font of the chart's SVG at `ref` (family and
 * size as computed there, semibold when emphasised), read after mount and
 * whenever `width` changes, and again once web fonts have loaded. Until
 * then, and where no canvas exists, the width is estimated per character.
 */
function useMeasureText(
  ref: RefObject<SVGSVGElement | null>,
  width: number,
): MeasureText {
  const [font, setFont] = useState<ChartFont | null>(null)
  const [fontsLoaded, setFontsLoaded] = useState(0)
  useEffect(() => {
    const node = ref.current
    if (!node) return
    const style = getComputedStyle(node)
    const family = style.fontFamily || 'sans-serif'
    const size = parseFloat(style.fontSize) || DEFAULT_FONT_SIZE
    setFont((prev) =>
      prev?.family === family && prev.size === size ? prev : { family, size },
    )
  }, [ref, width])
  useEffect(() => {
    let live = true
    document.fonts?.ready.then(() => {
      if (live) setFontsLoaded((n) => n + 1)
    })
    return () => {
      live = false
    }
  }, [])
  return useMemo(() => {
    const context = font ? measuringContext2d() : null
    const size = font?.size ?? DEFAULT_FONT_SIZE
    const cache = new Map<string, number>()
    return (text, bold) => {
      if (!context || !font)
        return (
          text.length * size * (bold ? FALLBACK_BOLD_CHAR_EM : FALLBACK_CHAR_EM)
        )
      const key = `${bold ? 1 : 0}${text}`
      let measured = cache.get(key)
      if (measured === undefined) {
        context.font = `${bold ? 600 : 400} ${font.size}px ${font.family}`
        measured = context.measureText(text).width
        cache.set(key, measured)
      }
      return measured
    }
    // fontsLoaded only invalidates the cache.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [font, fontsLoaded])
}

/**
 * The label if it fits `maxWidth`, else its start and end around a middle
 * ellipsis (the end of a system key often tells two systems apart).
 */
export function fitLabel(
  label: string,
  maxWidth: number,
  measure: MeasureText,
  bold = false,
): string {
  if (measure(label, bold) <= maxWidth) return label
  let best = '…'
  let low = 1
  let high = label.length - 1
  while (low <= high) {
    const kept = Math.floor((low + high) / 2)
    const head = Math.ceil(kept / 2)
    const candidate = `${label.slice(0, head)}…${label.slice(label.length - (kept - head))}`
    if (measure(candidate, bold) <= maxWidth) {
      best = candidate
      low = kept + 1
    } else {
      high = kept - 1
    }
  }
  return best
}

export function ForestPlot({
  rows,
  nullValue = 0,
  band = null,
  ariaLabel,
  axisLabel,
  legend,
  mode = 'point',
  className,
  'data-testid': testId = 'forest-plot',
}: ForestPlotProps) {
  const { locale } = useI18n()
  const [containerRef, measured] = useMeasuredWidth()
  const svgRef = useRef<SVGSVGElement>(null)
  const width = measured > 0 ? measured : FALLBACK_WIDTH
  const measureText = useMeasureText(svgRef, width)
  const compact = width < 560
  const finite = (v: number | null | undefined): v is number =>
    typeof v === 'number' && Number.isFinite(v)
  const valueText = (row: ForestPlotRow) =>
    finite(row.estimate)
      ? `${formatNumber(row.estimate, locale)} ${finite(row.lower) && finite(row.upper) ? formatInterval(row.lower, row.upper, locale) : ''}`.trim()
      : ''
  const longestValue = Math.max(0, ...rows.map((r) => valueText(r).length))
  const valueWidth = compact
    ? 0
    : Math.min(
        MAX_VALUE_WIDTH,
        Math.max(
          MIN_VALUE_WIDTH,
          Math.ceil(longestValue * MONO_CHAR_WIDTH) + VALUE_GAP,
        ),
      )
  const domainValues: (number | null | undefined)[] = []
  for (const row of rows) {
    domainValues.push(row.estimate, row.lower, row.upper)
    if (row.inner) domainValues.push(row.inner.lower, row.inner.upper)
  }
  if (nullValue !== null && nullValue !== undefined)
    domainValues.push(nullValue)
  if (band) domainValues.push(band.lower, band.upper)
  // Bars start at 0, so it is always on the axis.
  const barBase = mode === 'bar' ? 0 : null
  if (barBase !== null) domainValues.push(barBase)
  const { min, max, ticks } = axisTicks(domainValues)
  // The outer tick labels are centred on the plot's ends and must not
  // stick out of the SVG.
  const tickHalf = (tick: number | undefined) =>
    tick === undefined
      ? 0
      : measureText(formatNumber(tick, locale, 3), false) / 2
  const plotRight = Math.min(
    width - valueWidth - 12,
    width - EDGE - Math.ceil(tickHalf(ticks[ticks.length - 1])),
  )
  // The label column fits the longest label; past its maximum every label
  // goes on its own line above its row.
  const longestLabel = Math.max(
    0,
    ...rows.map((r) => measureText(r.label, Boolean(r.emphasis))),
  )
  const maxLabelWidth = Math.min(
    MAX_LABEL_WIDTH,
    Math.round(width * MAX_LABEL_SHARE),
    plotRight - MIN_PLOT_WIDTH - LABEL_GAP - EDGE,
  )
  const stacked = longestLabel > maxLabelWidth
  const labelRight = stacked
    ? EDGE
    : EDGE + Math.max(MIN_LABEL_WIDTH, Math.ceil(longestLabel))
  const plotLeft = Math.max(
    stacked ? 2 * EDGE : labelRight + LABEL_GAP,
    EDGE + Math.ceil(tickHalf(ticks[0])),
  )
  const plotWidth = Math.max(40, plotRight - plotLeft)
  const rowHeight = stacked ? STACKED_ROW_HEIGHT : ROW_HEIGHT
  const rowTop = (i: number) => TOP_PAD + i * rowHeight
  const plotBottom = TOP_PAD + rows.length * rowHeight
  const height = plotBottom + AXIS_HEIGHT
  // Vertical marks (grid, null value, band) leave the stacked labels' line free.
  const lineSpans: [number, number][] = stacked
    ? rows.map((_, i) => [
        rowTop(i) + STACKED_MARK_TOP,
        rowTop(i) + STACKED_ROW_HEIGHT,
      ])
    : [[TOP_PAD, plotBottom]]

  const x = (value: number) =>
    plotLeft + ((value - min) / (max - min || 1)) * plotWidth
  const clampX = (value: number) =>
    Math.min(plotLeft + plotWidth, Math.max(plotLeft, x(value)))

  return (
    <div className={className}>
      <div ref={containerRef} className="w-full">
        <svg
          ref={svgRef}
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
                y={rowTop(i)}
                width={width}
                height={rowHeight}
                className="fill-zinc-50 dark:fill-zinc-800/40"
              />
            ) : null,
          )}
          {band &&
            lineSpans.map(([y1, y2], j) => (
              <rect
                key={`band-${y1}`}
                data-testid={j === 0 ? 'forest-plot-band' : undefined}
                x={clampX(band.lower)}
                y={y1}
                width={Math.max(0, clampX(band.upper) - clampX(band.lower))}
                height={y2 - y1}
                className="fill-emerald-500/15 dark:fill-emerald-400/15"
              >
                {band.label && <title>{band.label}</title>}
              </rect>
            ))}
          {ticks.map((tick) => (
            <g key={`tick-${tick}`}>
              {lineSpans.map(([y1, y2]) => (
                <line
                  key={y1}
                  x1={x(tick)}
                  x2={x(tick)}
                  y1={y1}
                  y2={y2}
                  className="stroke-zinc-200 dark:stroke-zinc-800"
                  strokeWidth={1}
                />
              ))}
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
              <g>
                {lineSpans.map(([y1, y2], j) => (
                  <line
                    key={y1}
                    data-testid={j === 0 ? 'forest-plot-null' : undefined}
                    x1={x(nullValue)}
                    x2={x(nullValue)}
                    y1={y1}
                    y2={y2}
                    strokeDasharray="4 3"
                    strokeWidth={1.25}
                    className="stroke-zinc-500 dark:stroke-zinc-400"
                  />
                ))}
              </g>
            )}
          {rows.map((row, i) => {
            const cy = rowTop(i) + (stacked ? STACKED_MARK_Y : ROW_HEIGHT / 2)
            const has =
              typeof row.estimate === 'number' && Number.isFinite(row.estimate)
            const hasInterval =
              typeof row.lower === 'number' &&
              typeof row.upper === 'number' &&
              Number.isFinite(row.lower) &&
              Number.isFinite(row.upper)
            // A side label always fits its column; a stacked one may need
            // shortening to the full width.
            const label = stacked
              ? fitLabel(
                  row.label,
                  width - 2 * EDGE,
                  measureText,
                  Boolean(row.emphasis),
                )
              : row.label
            return (
              <g key={row.id} data-testid="forest-plot-row">
                <text
                  data-testid="forest-plot-label"
                  x={labelRight}
                  y={stacked ? rowTop(i) + STACKED_LABEL_BASELINE : cy + 4}
                  textAnchor={stacked ? 'start' : 'end'}
                  className={
                    row.emphasis
                      ? 'fill-zinc-900 font-semibold dark:fill-white'
                      : 'fill-zinc-700 dark:fill-zinc-300'
                  }
                >
                  {label !== row.label && <title>{row.label}</title>}
                  {label}
                </text>
                {has && barBase !== null && (
                  <rect
                    data-testid="forest-plot-bar"
                    x={Math.min(
                      clampX(barBase),
                      clampX(row.estimate as number),
                    )}
                    y={cy - 7}
                    width={Math.abs(
                      clampX(row.estimate as number) - clampX(barBase),
                    )}
                    height={14}
                    rx={2}
                    className={
                      row.emphasis
                        ? 'fill-emerald-600/80 dark:fill-emerald-400/80'
                        : 'fill-emerald-500/50 dark:fill-emerald-400/45'
                    }
                  />
                )}
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
                {has && barBase === null && (
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
                    {valueText(row)}
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
