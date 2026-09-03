'use client'

import { useMemo } from 'react'
import { Bar, BarChart, CartesianGrid, ErrorBar, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { formatAxisValue, formatCount, formatMetricValue, scaleMax } from '@/lib/reports/format'
import type { RankedRow } from '@/lib/reports/select'
import type { ReportMetricScale } from '@/types/report'
import {
  AXIS_LINE,
  AXIS_TICK,
  CHART_WRAPPER_CLASS,
  GRID_STROKE_OPACITY,
  SERIES_COLOR,
  type TranslateFn,
} from './chartTheme'
import { ChartTooltipBox } from './ChartTooltip'
import { SubHeading } from './ReportSection'

export interface MeanBarDatum {
  id: string
  label: string
  rank: number
  mean: number
  std: number
  n: number
  kind: 'model' | 'human'
}

interface MeanBarChartProps {
  rows: RankedRow[]
  scale: ReportMetricScale
  metricLabel: string
  locale: string
  t: TranslateFn
}

interface TooltipPayload {
  active?: boolean
  payload?: Array<{ payload: MeanBarDatum }>
}

export function MeanBarTooltip({
  active,
  payload,
  scale,
  locale,
  t,
  metricLabel,
}: TooltipPayload & { scale: ReportMetricScale; locale: string; t: TranslateFn; metricLabel: string }) {
  if (!active || !payload || payload.length === 0) return null
  const d = payload[0].payload
  return (
    <ChartTooltipBox
      title={`${d.rank}. ${d.label}`}
      lines={[
        { label: metricLabel, value: formatMetricValue(d.mean, scale, locale) },
        { label: t('reports.view.stdDev', 'Standardabweichung'), value: formatMetricValue(d.std, scale, locale) },
        { label: 'n', value: formatCount(d.n, locale) },
      ]}
    />
  )
}

/** Axis tick formatter bound to a scale/locale (kept outside JSX for testability). */
export function makeTickFormatter(scale: ReportMetricScale, locale: string) {
  return (value: number) => formatAxisValue(value, scale, locale)
}

export function toMeanBarData(rows: RankedRow[]): MeanBarDatum[] {
  return rows.map((row) => ({
    id: row.subject.id,
    label: row.subject.label,
    rank: row.rank,
    mean: row.primary.mean,
    std: row.primary.std ?? 0,
    n: row.primary.n,
    kind: row.subject.kind,
  }))
}

/** Horizontal bars (mean ± std) in ranking order for the primary metric. */
export function MeanBarChart({ rows, scale, metricLabel, locale, t }: MeanBarChartProps) {
  const data = useMemo(() => toMeanBarData(rows), [rows])
  if (data.length === 0) return null
  const max = scaleMax(scale)
  const height = Math.max(160, data.length * 36 + 48)
  return (
    <div className="mb-8" data-testid="mean-bar-chart">
      <SubHeading>
        {t('reports.view.meanByModel', '{metric} je Modell (Mittelwert ± Standardabweichung)', { metric: metricLabel })}
      </SubHeading>
      <div className={CHART_WRAPPER_CLASS}>
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, left: 8, bottom: 4 }} barCategoryGap="25%">
            <CartesianGrid horizontal={false} stroke="currentColor" strokeOpacity={GRID_STROKE_OPACITY} />
            <XAxis
              type="number"
              domain={[0, max ?? 'auto']}
              tick={AXIS_TICK}
              axisLine={AXIS_LINE}
              tickLine={false}
              tickFormatter={makeTickFormatter(scale, locale)}
            />
            <YAxis type="category" dataKey="label" width={160} tick={AXIS_TICK} axisLine={false} tickLine={false} />
            <Tooltip
              cursor={{ fill: 'currentColor', fillOpacity: 0.06 }}
              content={<MeanBarTooltip scale={scale} locale={locale} t={t} metricLabel={metricLabel} />}
            />
            <Bar dataKey="mean" fill={SERIES_COLOR.model} radius={[0, 4, 4, 0]} isAnimationActive={false}>
              <ErrorBar dataKey="std" direction="x" width={4} strokeWidth={1.5} stroke="currentColor" />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
