'use client'

import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { formatCount, formatNumber } from '@/lib/reports/format'
import type { SubjectDistribution } from '@/lib/reports/select'
import { AXIS_LINE, AXIS_TICK, CHART_WRAPPER_CLASS, SERIES_COLOR, type TranslateFn } from './chartTheme'
import { ChartTooltipBox } from './ChartTooltip'
import { SubHeading } from './ReportSection'

interface PerSubjectDistributionProps {
  subjects: SubjectDistribution[]
  valueLabel: string
  locale: string
  t: TranslateFn
}

interface TooltipPayload {
  active?: boolean
  payload?: Array<{ payload: SubjectDistribution['bins'][number] }>
}

export function SubjectBinTooltip({
  active,
  payload,
  locale,
  t,
  valueLabel,
}: TooltipPayload & { locale: string; t: TranslateFn; valueLabel: string }) {
  if (!active || !payload || payload.length === 0) return null
  const bin = payload[0].payload
  return (
    <ChartTooltipBox
      title={`${valueLabel} ${bin.label}`}
      lines={[
        { label: t('reports.view.shareShort', 'Anteil'), value: `${formatNumber(bin.pct, locale, 1)} %` },
        { label: t('reports.view.count', 'Anzahl'), value: formatCount(bin.count, locale) },
      ]}
    />
  )
}

/** Small multiples: one mini histogram per top-ranked subject (shares, common y-axis). */
export function PerSubjectDistribution({ subjects, valueLabel, locale, t }: PerSubjectDistributionProps) {
  if (subjects.length === 0) return null
  const yMax = Math.max(10, ...subjects.flatMap((s) => s.bins.map((b) => b.pct)))
  return (
    <div className="mb-8" data-testid="per-subject-distribution">
      <SubHeading>{t('reports.view.perSubjectDistribution', 'Verteilung je Modell')}</SubHeading>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {subjects.map((subject) => (
          <div
            key={subject.id}
            className="rounded-md border border-zinc-200 p-3 dark:border-zinc-800"
            data-testid="subject-histogram"
          >
            <div className="mb-1 flex items-baseline justify-between gap-2">
              <span className="truncate text-sm font-medium text-zinc-900 dark:text-white">{subject.label}</span>
              <span className="shrink-0 text-xs text-zinc-500 dark:text-zinc-400">
                {t('reports.view.samples', 'n = {n}', { n: formatCount(subject.total, locale) })}
              </span>
            </div>
            <div className={CHART_WRAPPER_CLASS}>
              <ResponsiveContainer width="100%" height={120}>
                <BarChart data={subject.bins} margin={{ top: 4, right: 4, left: -20, bottom: 0 }} barCategoryGap="15%">
                  <XAxis
                    dataKey="label"
                    tick={{ ...AXIS_TICK, fontSize: 10 }}
                    axisLine={AXIS_LINE}
                    tickLine={false}
                    interval="preserveStartEnd"
                  />
                  <YAxis domain={[0, Math.ceil(yMax)]} tick={{ ...AXIS_TICK, fontSize: 10 }} axisLine={false} tickLine={false} />
                  <Tooltip
                    cursor={{ fill: 'currentColor', fillOpacity: 0.06 }}
                    content={<SubjectBinTooltip locale={locale} t={t} valueLabel={valueLabel} />}
                  />
                  <Bar dataKey="pct" fill={SERIES_COLOR.model} radius={[3, 3, 0, 0]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        ))}
      </div>
      <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
        {t('reports.view.perSubjectHint', 'Anteil der Abgaben je {value}, gleiche Achse für alle Modelle.', { value: valueLabel })}
      </p>
    </div>
  )
}
