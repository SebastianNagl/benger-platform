'use client'

/**
 * Profile chart: estimates over an ordered or numeric x (a scope column of
 * the estimates, such as a position or a numeric factor), one line per
 * series with its intervals, one panel per facet on a shared scale, an
 * optional fitted slope (dashed), an optional reference slope (dotted) and
 * an optional shaded band per panel with its midpoint (e.g. the range an
 * ideal answer may take). Lines carry direct labels at their ends, so the
 * colours never carry meaning alone.
 *
 * It draws the data it is given (`@/lib/analysis/profile` builds it from
 * stored estimates) and computes nothing statistical.
 */

import { useI18n } from '@/contexts/I18nContext'
import { shortenLabel } from '@/lib/analysis/labels'
import type {
  ProfileData,
  ProfileLine,
  ProfilePanel,
  ProfileSlope,
} from '@/lib/analysis/profile'
import { axisTicks, formatNumber, MISSING } from '@/lib/analysis/results'
import clsx from 'clsx'
import { useId, useState } from 'react'
import {
  AXIS_TEXT,
  BASE_LINE,
  ChartTooltip,
  GRID_LINE,
  seriesSlot,
  useMeasuredWidth,
  type TooltipState,
} from './chartParts'

const HEIGHT = 240
const LABEL_GAP = 12
const PAD = { top: 14, bottom: 34, left: 48 }
/** Width of one character of the 12 px labels. */
const CHAR_WIDTH = 6.6
/** Most room right of the plot for the direct labels. */
const MAX_LABEL_ROOM = 160
/** Panels side by side from this container width on. */
const TWO_COLUMNS_FROM = 640

type Ticks = ReturnType<typeof axisTicks>

function labelRoom(lines: readonly ProfileLine[], width: number): number {
  const longest = Math.max(0, ...lines.map((l) => l.label.length))
  const cap = Math.min(MAX_LABEL_ROOM, Math.max(40, width * 0.3))
  return Math.min(cap, Math.max(24, longest * CHAR_WIDTH + 14))
}

function slopeLine(data: ProfileData, slope: number, xs: Ticks) {
  return [xs.min, xs.max].map((gx) => ({
    gx,
    gy: data.yMean + slope * (gx - data.xMean),
  }))
}

function Panel({
  panel,
  data,
  slope,
  reference,
  xs,
  ys,
  width,
  seriesKeys,
  showTitle,
}: {
  panel: ProfilePanel
  data: ProfileData
  slope: ProfileSlope | null
  reference: ProfileSlope | null
  xs: Ticks
  ys: Ticks
  width: number
  /** Every series of the chart in legend order (the colour slots). */
  seriesKeys: string[]
  showTitle: boolean
}) {
  const { t, locale } = useI18n()
  const [tip, setTip] = useState<TooltipState | null>(null)
  const clipId = `profile-clip-${useId().replace(/[^A-Za-z0-9_-]/g, '')}`
  const right = labelRoom(panel.lines, width)
  const plotW = Math.max(60, width - PAD.left - right)
  const plotH = HEIGHT - PAD.top - PAD.bottom
  const x = (v: number) => PAD.left + ((v - xs.min) / (xs.max - xs.min)) * plotW
  const y = (v: number) =>
    PAD.top + plotH - ((v - ys.min) / (ys.max - ys.min)) * plotH
  const clampY = (v: number) => Math.min(ys.max, Math.max(ys.min, v))
  const fmt = (v: number | null) => formatNumber(v, locale, 3)
  const xText = (v: number) => (data.xLevels ? (data.xLevels[v] ?? '') : fmt(v))
  const band = panel.band ?? []
  // Direct labels at the line ends, pushed apart so they never overlap.
  const labelY = new Map<number, number>()
  panel.lines
    .map((line, i) => {
      const last = line.points[line.points.length - 1]
      return last ? { i, y: y(clampY(last.estimate)) + 4 } : null
    })
    .filter((e): e is { i: number; y: number } => e !== null)
    .sort((a, b) => a.y - b.y)
    .forEach((e, k, all) => {
      const prev = k > 0 ? labelY.get(all[k - 1].i)! : -Infinity
      labelY.set(e.i, Math.max(e.y, prev + LABEL_GAP))
    })
  const straight = (
    s: ProfileSlope,
    className: string,
    dash: string,
    testId: string,
  ) => {
    const [a, b] = slopeLine(data, s.slope, xs)
    return (
      <line
        x1={x(a.gx)}
        y1={y(a.gy)}
        x2={x(b.gx)}
        y2={y(b.gy)}
        strokeDasharray={dash}
        strokeLinecap="round"
        strokeWidth={1.4}
        className={className}
        data-testid={testId}
      />
    )
  }

  return (
    <div className="relative min-w-0" data-testid="profile-panel">
      {showTitle && (
        <p
          className="mb-1 truncate font-mono text-xs text-zinc-600 dark:text-zinc-300"
          title={panel.title ?? undefined}
        >
          {panel.title ?? MISSING}
        </p>
      )}
      <svg
        width={width}
        height={HEIGHT}
        className="block text-xs"
        role="img"
        aria-label={t('analysis.views.profile.panelAria', {
          panel: panel.title ?? '',
        })}
        onMouseLeave={() => setTip(null)}
      >
        <defs>
          <clipPath id={clipId}>
            <rect x={PAD.left} y={PAD.top} width={plotW} height={plotH} />
          </clipPath>
        </defs>
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
            {xText(tick)}
          </text>
        ))}
        {band.length > 1 && (
          <g data-testid="profile-band">
            <path
              d={
                band
                  .map(
                    (b, i) => `${i ? 'L' : 'M'}${x(b.x)},${y(clampY(b.high))}`,
                  )
                  .join('') +
                [...band]
                  .reverse()
                  .map((b) => `L${x(b.x)},${y(clampY(b.low))}`)
                  .join('') +
                'Z'
              }
              className="fill-emerald-500/15 dark:fill-emerald-400/15"
            />
            <path
              d={band
                .map(
                  (b, i) =>
                    `${i ? 'L' : 'M'}${x(b.x)},${y(clampY((b.low + b.high) / 2))}`,
                )
                .join('')}
              fill="none"
              strokeDasharray="2 3"
              strokeWidth={1.5}
              className="stroke-emerald-700/70 dark:stroke-emerald-400/70"
            />
          </g>
        )}
        <g clipPath={`url(#${clipId})`}>
          {reference &&
            straight(
              reference,
              'stroke-zinc-400 dark:stroke-zinc-500',
              '1 4',
              'profile-reference',
            )}
          {slope &&
            straight(
              slope,
              'stroke-zinc-700 dark:stroke-zinc-300',
              '6 4',
              'profile-slope',
            )}
        </g>
        {panel.lines.map((line, li) => {
          const slot = seriesSlot(seriesKeys.indexOf(line.key))
          const pts = line.points
          const last = pts[pts.length - 1]
          return (
            <g key={line.key || li} data-testid="profile-line">
              {pts.map((p) =>
                p.lower !== null && p.upper !== null ? (
                  <line
                    key={`ci${p.x}`}
                    x1={x(p.x)}
                    x2={x(p.x)}
                    y1={y(clampY(p.lower))}
                    y2={y(clampY(p.upper))}
                    strokeWidth={1.5}
                    className={slot.stroke}
                    opacity={0.6}
                  />
                ) : null,
              )}
              <path
                d={pts
                  .map(
                    (p, i) =>
                      `${i ? 'L' : 'M'}${x(p.x)},${y(clampY(p.estimate))}`,
                  )
                  .join('')}
                fill="none"
                strokeWidth={2}
                strokeLinejoin="round"
                className={slot.stroke}
              />
              {pts.map((p) => (
                <circle
                  key={`pt${p.x}`}
                  cx={x(p.x)}
                  cy={y(clampY(p.estimate))}
                  r={4}
                  strokeWidth={2}
                  className={clsx(
                    slot.fill,
                    'stroke-white dark:stroke-zinc-900',
                  )}
                  onMouseMove={(e) => {
                    const box = (
                      e.currentTarget.ownerSVGElement as SVGSVGElement
                    ).getBoundingClientRect()
                    setTip({
                      x: e.clientX - box.left,
                      y: e.clientY - box.top,
                      content: (
                        <>
                          <span className="font-medium">{line.title}</span>
                          <br />
                          {t('analysis.views.profile.tip', {
                            x: xText(p.x),
                            estimate: fmt(p.estimate),
                            lower: fmt(p.lower),
                            upper: fmt(p.upper),
                            n: p.n ?? MISSING,
                          })}
                        </>
                      ),
                    })
                  }}
                />
              ))}
              {last && (
                <text
                  x={x(last.x) + 8}
                  y={labelY.get(li)}
                  className="fill-zinc-700 font-medium dark:fill-zinc-200"
                >
                  {shortenLabel(
                    line.label,
                    Math.floor((right - 14) / CHAR_WIDTH),
                  )}
                  <title>{line.title}</title>
                </text>
              )}
            </g>
          )
        })}
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
  )
}

export interface EstimateProfileChartProps {
  data: ProfileData
  /** What x is (the scope column, a factor). */
  xLabel: string
  /** What the estimates are (the outcome). */
  yLabel: string
  /** A fitted slope, drawn dashed through the points' means. */
  slope?: ProfileSlope | null
  /** A reference slope (e.g. the smallest response that matters), dotted. */
  reference?: ProfileSlope | null
  /** Legend text of the panels' band, shown when a panel has one. */
  bandLabel?: string
  /** Shown when there is nothing to draw. */
  emptyMessage?: string
}

export function EstimateProfileChart({
  data,
  xLabel,
  yLabel,
  slope = null,
  reference = null,
  bandLabel,
  emptyMessage,
}: EstimateProfileChartProps) {
  const { t, locale } = useI18n()
  const { ref, width } = useMeasuredWidth()
  const panels = data.panels.filter((p) =>
    p.lines.some((l) => l.points.length > 0),
  )
  const columns = panels.length > 1 && width >= TWO_COLUMNS_FROM ? 2 : 1
  const panelWidth = Math.floor((width - (columns - 1) * 16) / columns)
  const values: number[] = []
  const xValues: number[] = []
  for (const p of panels) {
    for (const line of p.lines) {
      for (const pt of line.points) {
        values.push(pt.estimate)
        if (pt.lower !== null) values.push(pt.lower)
        if (pt.upper !== null) values.push(pt.upper)
        xValues.push(pt.x)
      }
    }
    for (const b of p.band ?? []) values.push(b.low, b.high)
  }
  const xs = data.xLevels
    ? {
        min: -0.5,
        max: Math.max(0.5, data.xLevels.length - 0.5),
        ticks: data.xLevels.map((_, i) => i),
      }
    : axisTicks(xValues, 5)
  // Both slopes span the x axis inside the y axis, so they are drawn at
  // their true angle; a reference slope also sets the scale a meaningful
  // response needs, so a flat profile does not look steep on a magnified axis.
  for (const s of [slope, reference]) {
    if (!s || !Number.isFinite(s.slope) || xValues.length === 0) continue
    for (const { gy } of slopeLine(data, s.slope, xs)) values.push(gy)
  }
  const ys = axisTicks(values, 5)
  const seriesKeys = [
    ...new Set(panels.flatMap((p) => p.lines.map((l) => l.key))),
  ]
  const seriesTitle = (key: string) =>
    panels.flatMap((p) => p.lines).find((l) => l.key === key)?.title ?? key
  const hasBand = panels.some((p) => (p.band ?? []).length > 1)

  if (panels.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-zinc-500 dark:text-zinc-400">
        {emptyMessage ?? t('analysis.views.profile.empty')}
      </p>
    )
  }

  return (
    <div data-testid="estimate-profile-chart">
      <div
        ref={ref}
        className={clsx(
          'grid w-full min-w-0 gap-4',
          columns === 2 && 'grid-cols-2',
        )}
      >
        {panels.map((panel) => (
          <Panel
            key={panel.key}
            panel={panel}
            data={data}
            slope={slope}
            reference={reference}
            xs={xs}
            ys={ys}
            width={panelWidth}
            seriesKeys={seriesKeys}
            showTitle={panels.length > 1 || panel.title !== null}
          />
        ))}
      </div>
      <p className="mt-1 text-center text-xs text-zinc-500 dark:text-zinc-400">
        {t('analysis.views.profile.axis', { x: xLabel, y: yLabel })}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-zinc-600 dark:text-zinc-400">
        {seriesKeys.length > 1 &&
          seriesKeys.map((key, i) => (
            <span
              key={key || i}
              className="inline-flex min-w-0 items-center gap-2"
            >
              <span
                className={clsx(
                  'inline-block h-0.5 w-5 shrink-0 rounded',
                  seriesSlot(i).swatch,
                )}
                aria-hidden="true"
              />
              <span className="[overflow-wrap:anywhere]">
                {seriesTitle(key)}
              </span>
            </span>
          ))}
        {slope && (
          <span className="inline-flex items-center gap-2">
            <svg width="20" height="6" aria-hidden="true">
              <line
                x1="0"
                y1="3"
                x2="20"
                y2="3"
                strokeDasharray="6 4"
                strokeWidth={1.4}
                className="stroke-zinc-700 dark:stroke-zinc-300"
              />
            </svg>
            {t('analysis.views.profile.slope', {
              label: slope.label,
              slope: formatNumber(slope.slope, locale, 3),
            })}
          </span>
        )}
        {reference && (
          <span className="inline-flex items-center gap-2">
            <svg width="20" height="6" aria-hidden="true">
              <line
                x1="1"
                y1="3"
                x2="19"
                y2="3"
                strokeDasharray="1 4"
                strokeLinecap="round"
                strokeWidth={1.5}
                className="stroke-zinc-400 dark:stroke-zinc-500"
              />
            </svg>
            {reference.label}
          </span>
        )}
        {hasBand && (
          <span className="inline-flex items-center gap-2">
            <span
              className="inline-block h-3 w-5 rounded-sm bg-emerald-500/15 ring-1 ring-emerald-500/30 dark:bg-emerald-400/15"
              aria-hidden="true"
            />
            {bandLabel ?? t('analysis.views.profile.band')}
          </span>
        )}
      </div>
    </div>
  )
}
