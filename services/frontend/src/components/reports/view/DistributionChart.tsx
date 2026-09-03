'use client'

import clsx from 'clsx'
import { useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatCount, formatNumber } from '@/lib/reports/format'
import { toPercentSeries, type PercentBin } from '@/lib/reports/select'
import type { ReportDistribution } from '@/types/report'
import {
  AXIS_LINE,
  AXIS_TICK,
  CHART_WRAPPER_CLASS,
  GRID_STROKE_OPACITY,
  LEGEND_SWATCH_CLASS,
  SERIES_COLOR,
  type TranslateFn,
} from './chartTheme'
import { ChartLegend, ChartTooltipBox } from './ChartTooltip'
import { SubHeading } from './ReportSection'

export type DistributionMode = 'count' | 'share'

interface DistributionChartProps {
  distribution: ReportDistribution
  /** Axis label for the binned value ("Notenpunkte", "Punkte"). */
  valueLabel: string
  title: string
  locale: string
  t: TranslateFn
  defaultMode?: DistributionMode
}

interface TooltipPayload {
  active?: boolean
  payload?: Array<{ payload: PercentBin }>
}

export function DistributionTooltip({
  active,
  payload,
  mode,
  locale,
  t,
  valueLabel,
  showHumans = true,
}: TooltipPayload & { mode: DistributionMode; locale: string; t: TranslateFn; valueLabel: string; showHumans?: boolean }) {
  if (!active || !payload || payload.length === 0) return null
  const bin = payload[0].payload
  const fmt = (count: number, pct: number) =>
    mode === 'share'
      ? `${formatNumber(pct, locale, 1)} % (${formatCount(count, locale)})`
      : formatCount(count, locale)
  return (
    <ChartTooltipBox
      title={`${valueLabel} ${bin.label}`}
      lines={[
        { label: t('reports.view.models', 'Modelle'), value: fmt(bin.model, bin.modelPct), swatchClass: LEGEND_SWATCH_CLASS.model },
        ...(showHumans
          ? [{ label: t('reports.view.humans', 'Menschen'), value: fmt(bin.human, bin.humanPct), swatchClass: LEGEND_SWATCH_CLASS.human }]
          : []),
      ]}
    />
  )
}

/** Grouped histogram: models vs humans per bin, as counts or per-kind shares. */
export function DistributionChart({
  distribution,
  valueLabel,
  title,
  locale,
  t,
  defaultMode = 'share',
}: DistributionChartProps) {
  const [mode, setMode] = useState<DistributionMode>(defaultMode)
  const data = useMemo(() => toPercentSeries(distribution), [distribution])
  const hasHumans = data.some((d) => d.human > 0)
  const hasModels = data.some((d) => d.model > 0)
  const modelKey = mode === 'share' ? 'modelPct' : 'model'
  const humanKey = mode === 'share' ? 'humanPct' : 'human'
  const yLabel = mode === 'share' ? t('reports.view.share', 'Anteil (%)') : t('reports.view.count', 'Anzahl')

  return (
    <div className="mb-8" data-testid="distribution-chart" data-mode={mode}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <SubHeading>{title}</SubHeading>
        <div
          role="radiogroup"
          aria-label={t('reports.view.displayMode', 'Darstellung')}
          className="inline-flex overflow-hidden rounded-md border border-zinc-300 text-xs dark:border-zinc-700"
        >
          {(['count', 'share'] as DistributionMode[]).map((m) => (
            <button
              key={m}
              type="button"
              role="radio"
              aria-checked={mode === m}
              onClick={() => setMode(m)}
              className={clsx(
                'px-3 py-1 transition',
                mode === m
                  ? 'bg-zinc-800 font-medium text-white dark:bg-zinc-200 dark:text-zinc-900'
                  : 'bg-white text-zinc-600 hover:bg-zinc-50 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800',
              )}
            >
              {m === 'count' ? t('reports.view.count', 'Anzahl') : t('reports.view.shareShort', 'Anteil')}
            </button>
          ))}
        </div>
      </div>
      <div className={CHART_WRAPPER_CLASS}>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 8 }} barGap={2} barCategoryGap="20%">
            <CartesianGrid vertical={false} stroke="currentColor" strokeOpacity={GRID_STROKE_OPACITY} />
            <XAxis
              dataKey="label"
              tick={AXIS_TICK}
              axisLine={AXIS_LINE}
              tickLine={false}
              interval="preserveStartEnd"
              label={{ value: valueLabel, position: 'insideBottom', offset: -4, fill: 'currentColor', fontSize: 12 }}
            />
            <YAxis
              tick={AXIS_TICK}
              axisLine={false}
              tickLine={false}
              width={44}
              label={{ value: yLabel, angle: -90, position: 'insideLeft', fill: 'currentColor', fontSize: 12 }}
            />
            <Tooltip
              cursor={{ fill: 'currentColor', fillOpacity: 0.06 }}
              content={<DistributionTooltip mode={mode} locale={locale} t={t} valueLabel={valueLabel} showHumans={hasHumans} />}
            />
            <Bar
              dataKey={modelKey}
              name={t('reports.view.models', 'Modelle')}
              fill={SERIES_COLOR.model}
              radius={[4, 4, 0, 0]}
              isAnimationActive={false}
            />
            {hasHumans && (
              <Bar
                dataKey={humanKey}
                name={t('reports.view.humans', 'Menschen')}
                fill={SERIES_COLOR.human}
                radius={[4, 4, 0, 0]}
                isAnimationActive={false}
              />
            )}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ChartLegend
        items={[
          { label: t('reports.view.models', 'Modelle'), swatchClass: LEGEND_SWATCH_CLASS.model },
          ...(hasHumans ? [{ label: t('reports.view.humans', 'Menschen'), swatchClass: LEGEND_SWATCH_CLASS.human }] : []),
        ]}
      />
      {!hasHumans && hasModels && (
        <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
          {t('reports.view.noHumanSamples', 'Keine menschlichen Abgaben in dieser Auswertung.')}
        </p>
      )}
    </div>
  )
}
