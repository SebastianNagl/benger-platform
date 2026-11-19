'use client'

/**
 * Distribution of a set of values (for example the paired differences of
 * one contrast): one bar per exact value (discrete outcomes give many exact
 * ties) or per bin, a dashed line at the reference value, the mean marked
 * on the axis, the counts in a hover tooltip and a summary below the chart
 * (count, mean and median, values at, above and below the reference).
 *
 * It draws the counts it is given and computes nothing statistical.
 */

import { useI18n } from '@/contexts/I18nContext'
import { axisTicks, formatLevel, formatNumber } from '@/lib/analysis/results'
import { useState } from 'react'
import {
  AXIS_TEXT,
  BASE_LINE,
  ChartTooltip,
  GRID_LINE,
  REF_LINE,
  SERIES,
  useMeasuredWidth,
  type TooltipState,
} from './chartParts'

/** Counts per exact value: `[value, count]`, values ascending. */
export interface ExactHistogram {
  kind: 'exact'
  values: [number, number][]
}

/** Counts per bin: `[low, high, count]`, bins ascending. */
export interface BinnedHistogram {
  kind: 'bins'
  bins: [number, number, number][]
}

export interface ValueDistribution {
  histogram: ExactHistogram | BinnedHistogram
  /** Number of values. */
  n: number
  /** Number of groups the values come from (e.g. units), if known. */
  groups?: number | null
  mean?: number | null
  median?: number | null
  /** Values equal to, above and below the reference value. */
  atReference?: number | null
  above?: number | null
  below?: number | null
}

interface Bar {
  lo: number
  hi: number
  center: number
  count: number
  exact: boolean
}

/** The bars of a histogram; exact values get bars 80 % of the closest gap wide. */
export function barsOf(histogram: ValueDistribution['histogram']): Bar[] {
  if (histogram.kind === 'exact') {
    const values = histogram.values.map(([v]) => v)
    let gap = Infinity
    for (let i = 1; i < values.length; i++) {
      gap = Math.min(gap, values[i] - values[i - 1])
    }
    const half = Number.isFinite(gap) && gap > 0 ? gap * 0.4 : 0.5
    return histogram.values.map(([v, count]) => ({
      lo: v - half,
      hi: v + half,
      center: v,
      count,
      exact: true,
    }))
  }
  return histogram.bins.map(([lo, hi, count]) => ({
    lo,
    hi,
    center: (lo + hi) / 2,
    count,
    exact: false,
  }))
}

const HEIGHT = 180
const PAD = { top: 12, right: 12, bottom: 34, left: 40 }

export interface ValueDistributionChartProps {
  data: ValueDistribution
  /** What the values are (the axis caption), e.g. "difference of share". */
  valueLabel: string
  /** The value the dashed line marks (default 0). */
  referenceValue?: number
}

export function ValueDistributionChart({
  data,
  valueLabel,
  referenceValue = 0,
}: ValueDistributionChartProps) {
  const { t, locale } = useI18n()
  const { ref, width } = useMeasuredWidth()
  const [tip, setTip] = useState<TooltipState | null>(null)
  const bars = barsOf(data.histogram)
  const xs = axisTicks(
    [...bars.flatMap((b) => [b.lo, b.hi]), referenceValue],
    6,
  )
  const maxCount = Math.max(1, ...bars.map((b) => b.count))
  const ys = axisTicks([0, maxCount], 4)
  const plotW = Math.max(60, width - PAD.left - PAD.right)
  const plotH = HEIGHT - PAD.top - PAD.bottom
  const x = (v: number) => PAD.left + ((v - xs.min) / (xs.max - xs.min)) * plotW
  const y = (c: number) => PAD.top + plotH - (c / ys.max) * plotH
  const fmt = (v: number | null | undefined) => formatNumber(v, locale, 3)
  const share = (n: number) => formatLevel(data.n ? n / data.n : 0, locale)
  const mean = typeof data.mean === 'number' ? data.mean : null

  const summary: [string, string][] = [
    [
      t('analysis.views.distribution.count'),
      typeof data.groups === 'number'
        ? t('analysis.views.distribution.countGroups', {
            n: data.n,
            groups: data.groups,
          })
        : String(data.n),
    ],
  ]
  if (mean !== null || typeof data.median === 'number') {
    summary.push([
      t('analysis.views.distribution.meanMedian'),
      `${fmt(mean)} · ${fmt(data.median)}`,
    ])
  }
  if (typeof data.atReference === 'number') {
    summary.push([
      t('analysis.views.distribution.atReference', {
        reference: fmt(referenceValue),
      }),
      `${data.atReference} (${share(data.atReference)})`,
    ])
  }
  if (typeof data.above === 'number' && typeof data.below === 'number') {
    summary.push([
      t('analysis.views.distribution.direction'),
      t('analysis.views.distribution.directionValue', {
        above: data.above,
        below: data.below,
      }),
    ])
  }

  return (
    <div data-testid="value-distribution-chart">
      <div ref={ref} className="relative w-full min-w-0">
        <svg
          width={width}
          height={HEIGHT}
          role="img"
          aria-label={t('analysis.views.distribution.aria', {
            n: data.n,
            mean: fmt(mean),
          })}
          className="block text-xs"
          onMouseLeave={() => setTip(null)}
        >
          {ys.ticks.map((tick) => (
            <g key={`y${tick}`}>
              <line
                x1={PAD.left}
                x2={PAD.left + plotW}
                y1={y(tick)}
                y2={y(tick)}
                className={GRID_LINE}
              />
              <text
                x={PAD.left - 6}
                y={y(tick) + 4}
                textAnchor="end"
                className={AXIS_TEXT}
              >
                {fmt(tick)}
              </text>
            </g>
          ))}
          {xs.ticks.map((tick) => (
            <text
              key={`x${tick}`}
              x={x(tick)}
              y={HEIGHT - PAD.bottom + 16}
              textAnchor="middle"
              className={AXIS_TEXT}
            >
              {fmt(tick)}
            </text>
          ))}
          {bars.map((b, i) => {
            const left = x(b.lo) + 1
            const w = Math.max(2, x(b.hi) - x(b.lo) - 2)
            const top = y(b.count)
            const h = Math.max(0, PAD.top + plotH - top)
            return (
              <g key={i} data-testid="distribution-bar">
                <path
                  d={`M${left},${top + h}V${top + Math.min(3, h)}q0,-3 3,-3h${Math.max(0, w - 6)}q3,0 3,3V${top + h}Z`}
                  className={SERIES[0].fill}
                />
                <rect
                  x={left - 1}
                  y={PAD.top}
                  width={w + 2}
                  height={plotH}
                  fill="transparent"
                  onMouseMove={(e) => {
                    const box = (
                      e.currentTarget.ownerSVGElement as SVGSVGElement
                    ).getBoundingClientRect()
                    setTip({
                      x: e.clientX - box.left,
                      y: e.clientY - box.top,
                      content: b.exact
                        ? t('analysis.views.distribution.tipExact', {
                            value: fmt(b.center),
                            count: b.count,
                          })
                        : t('analysis.views.distribution.tipBin', {
                            low: fmt(b.lo),
                            high: fmt(b.hi),
                            count: b.count,
                          }),
                    })
                  }}
                />
              </g>
            )
          })}
          <line
            x1={x(referenceValue)}
            x2={x(referenceValue)}
            y1={PAD.top}
            y2={PAD.top + plotH}
            strokeDasharray="4 3"
            className={REF_LINE}
            data-testid="distribution-reference"
          />
          {mean !== null && (
            <path
              d={`M${x(mean)},${PAD.top + plotH + 2}l-4,6h8Z`}
              className="fill-zinc-800 dark:fill-zinc-200"
              data-testid="distribution-mean"
            >
              <title>
                {t('analysis.views.distribution.meanMarker', {
                  value: fmt(mean),
                })}
              </title>
            </path>
          )}
          <line
            x1={PAD.left}
            x2={PAD.left + plotW}
            y1={PAD.top + plotH}
            y2={PAD.top + plotH}
            className={BASE_LINE}
          />
        </svg>
        <ChartTooltip tip={tip} width={width} />
      </div>
      <p className="mt-1 text-center text-xs text-zinc-500 dark:text-zinc-400">
        {valueLabel}
      </p>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-xs sm:grid-cols-4">
        {summary.map(([label, value]) => (
          <div key={label} className="min-w-0">
            <dt className="text-zinc-500 dark:text-zinc-400">{label}</dt>
            <dd className="font-medium text-zinc-900 tabular-nums dark:text-zinc-100">
              {value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
