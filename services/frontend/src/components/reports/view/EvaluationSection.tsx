'use client'

import {
  metricLabel,
  metricScale,
  type MetricRegistry,
} from '@/lib/reports/format'
import {
  configsForMetric,
  distributionFor,
  otherMetricColumns,
  rankSeries,
  selectPrimary,
  selectVisibleConfigs,
  topSubjectDistributions,
} from '@/lib/reports/select'
import type { ReportChartsConfig, ReportSnapshot } from '@/types/report'
import { useMemo, useState } from 'react'
import type { TranslateFn } from './chartTheme'
import { ConfigSelector } from './ConfigSelector'
import { DistributionChart } from './DistributionChart'
import { MeanBarChart } from './MeanBarChart'
import { MethodsList } from './MethodsList'
import { PerSubjectDistribution } from './PerSubjectDistribution'
import { RankingTable, type MetricColumn } from './RankingTable'
import { Prose, QuietNote, ReportSection, SubHeading } from './ReportSection'

interface EvaluationSectionProps {
  snapshot: ReportSnapshot | null
  chartsConfig?: ReportChartsConfig | null
  interpretation?: string | null
  conclusions?: string | null
  registry: MetricRegistry
  locale: string
  t: TranslateFn
}

/** The evaluation heart of the report: methods, ranking tables, distributions, means. */
export function EvaluationSection({
  snapshot,
  chartsConfig,
  interpretation,
  conclusions,
  registry,
  locale,
  t,
}: EvaluationSectionProps) {
  const cfg = chartsConfig ?? undefined
  const visibleConfigs = useMemo(
    () => (snapshot ? selectVisibleConfigs(snapshot, cfg) : []),
    [snapshot, cfg],
  )
  const primary = useMemo(
    () =>
      snapshot
        ? selectPrimary(snapshot, cfg, visibleConfigs)
        : { metric: null, configId: null, gradeMetric: null },
    [snapshot, cfg, visibleConfigs],
  )
  const options = useMemo(
    () => configsForMetric(visibleConfigs, primary.metric),
    [visibleConfigs, primary.metric],
  )
  const [selected, setSelected] = useState<string | null>(null)
  const configId =
    selected && options.some((o) => o.id === selected)
      ? selected
      : primary.configId

  const hiddenSubjects = cfg?.hidden_subjects
  const hidden = useMemo(() => hiddenSubjects ?? [], [hiddenSubjects])
  const showHumans = cfg?.show_humans !== false
  const showDistribution = cfg?.show_distribution !== false

  const modelRows = useMemo(
    () =>
      snapshot
        ? rankSeries(snapshot.series, configId, primary.metric, 'model', hidden)
        : [],
    [snapshot, configId, primary.metric, hidden],
  )
  const humanRows = useMemo(
    () =>
      snapshot && showHumans
        ? rankSeries(snapshot.series, configId, primary.metric, 'human', hidden)
        : [],
    [snapshot, configId, primary.metric, hidden, showHumans],
  )

  const labelFor = (id: string) => metricLabel(id, snapshot?.methods, registry)
  const scaleFor = (id: string) => metricScale(id, snapshot?.methods, registry)
  const column = (id: string): MetricColumn => ({
    id,
    label: labelFor(id),
    scale: scaleFor(id),
  })

  const title = t('reports.view.evaluation')

  if (!snapshot) {
    return (
      <ReportSection title={title} id="evaluation">
        {interpretation && <Prose>{interpretation}</Prose>}
        <div className="mt-3">
          <QuietNote>{t('reports.view.noSnapshot')}</QuietNote>
        </div>
      </ReportSection>
    )
  }

  const usedMetricIds = new Set(visibleConfigs.map((c) => c.metric))
  const usedMethods = snapshot.methods.filter(
    (m) => usedMetricIds.has(m.id) && !m.derived,
  )
  const primaryColumn = primary.metric ? column(primary.metric) : null
  const otherModelColumns = otherMetricColumns(
    modelRows,
    primary.metric,
    primary.gradeMetric,
    cfg?.visible_metrics,
  ).map(column)
  const otherHumanColumns = otherMetricColumns(
    humanRows,
    primary.metric,
    primary.gradeMetric,
    cfg?.visible_metrics,
  ).map(column)

  const distMetric = primary.gradeMetric ?? primary.metric
  const distribution = showDistribution
    ? distributionFor(snapshot, configId, distMetric)
    : null
  const distValueLabel = primary.gradeMetric
    ? t('reports.view.gradePoints')
    : (primaryColumn?.label ?? '')
  const subjectDistributions = distribution
    ? topSubjectDistributions(modelRows, distribution, locale, 8)
    : []

  return (
    <ReportSection
      title={title}
      id="evaluation"
      aside={
        <ConfigSelector
          options={options}
          value={configId}
          onChange={setSelected}
          t={t}
        />
      }
    >
      <MethodsList
        methods={usedMethods}
        configs={visibleConfigs}
        labelFor={labelFor}
        locale={locale}
        t={t}
      />

      {interpretation && (
        <div className="mb-6">
          <SubHeading>{t('reports.view.interpretation')}</SubHeading>
          <Prose>{interpretation}</Prose>
        </div>
      )}

      {primaryColumn ? (
        <>
          <RankingTable
            title={t('reports.view.performanceByModel')}
            rows={modelRows}
            primary={primaryColumn}
            gradeMetric={primary.gradeMetric}
            otherColumns={otherModelColumns}
            subjectHeader={t('reports.view.model')}
            locale={locale}
            t={t}
            testId="ranking-table-models"
          />
          {showHumans && humanRows.length > 0 && (
            <RankingTable
              title={t('reports.view.performanceByHuman')}
              rows={humanRows}
              primary={primaryColumn}
              gradeMetric={primary.gradeMetric}
              otherColumns={otherHumanColumns}
              subjectHeader={t('reports.view.participant')}
              locale={locale}
              t={t}
              testId="ranking-table-humans"
            />
          )}
          {distribution && (
            <DistributionChart
              distribution={distribution}
              valueLabel={distValueLabel}
              title={
                distribution.by_kind.human.some((n) => n > 0)
                  ? primary.gradeMetric
                    ? t('reports.view.distributionTitle')
                    : t('reports.view.distributionTitleMetric', {
                        metric: primaryColumn.label,
                      })
                  : primary.gradeMetric
                    ? t('reports.view.distributionTitleModels')
                    : t('reports.view.distributionTitleMetricModels', {
                        metric: primaryColumn.label,
                      })
              }
              locale={locale}
              t={t}
            />
          )}
          {subjectDistributions.length > 0 && (
            <PerSubjectDistribution
              subjects={subjectDistributions}
              valueLabel={distValueLabel}
              locale={locale}
              t={t}
            />
          )}
          <MeanBarChart
            rows={modelRows}
            scale={primaryColumn.scale}
            metricLabel={primaryColumn.label}
            locale={locale}
            t={t}
          />
        </>
      ) : (
        <QuietNote>{t('reports.view.noSeries')}</QuietNote>
      )}

      {conclusions && (
        <div className="rounded-md bg-zinc-50 p-4 dark:bg-zinc-800/60">
          <SubHeading>{t('reports.view.conclusions')}</SubHeading>
          <Prose>{conclusions}</Prose>
        </div>
      )}
    </ReportSection>
  )
}
