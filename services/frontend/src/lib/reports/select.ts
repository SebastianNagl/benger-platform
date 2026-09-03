/**
 * Pure selection helpers for the report viewer: which configs/metrics are
 * visible, how subjects rank, and which distribution backs a chart.
 *
 * Everything here is deterministic over `ReportSnapshot` + `ReportChartsConfig`
 * so the page and its tests share one source of truth for ranking.
 */
import type {
  ReportChartsConfig,
  ReportConfigRef,
  ReportDistribution,
  ReportMetricScale,
  ReportMetricStats,
  ReportSeriesRow,
  ReportSnapshot,
  ReportSubject,
} from '@/types/report'

/** Suffixes of companion keys that never become table columns. */
const HIDDEN_KEY_SUFFIXES = ['_raw', '_passed', '_details']

export function isHiddenMetricKey(key: string): boolean {
  return HIDDEN_KEY_SUFFIXES.some((suffix) => key.endsWith(suffix))
}

/** Configs the report shows: `visible_configs` when set (and non-empty), else all. */
export function selectVisibleConfigs(
  snapshot: ReportSnapshot,
  chartsConfig: ReportChartsConfig | undefined,
): ReportConfigRef[] {
  const visible = chartsConfig?.visible_configs
  if (!Array.isArray(visible) || visible.length === 0) return snapshot.configs
  const allowed = new Set(visible)
  return snapshot.configs.filter((c) => allowed.has(c.id))
}

export interface PrimarySelection {
  metric: string | null
  configId: string | null
  gradeMetric: string | null
}

/**
 * Resolve the primary metric/config, honouring editor overrides and falling
 * back to the first visible config that scores the primary metric.
 */
export function selectPrimary(
  snapshot: ReportSnapshot,
  chartsConfig: ReportChartsConfig | undefined,
  visibleConfigs: ReportConfigRef[] = selectVisibleConfigs(snapshot, chartsConfig),
): PrimarySelection {
  const metric = chartsConfig?.primary_metric ?? snapshot.primary_metric ?? null
  if (!metric) return { metric: null, configId: null, gradeMetric: null }

  const candidates = configsForMetric(visibleConfigs, metric)
  const preferred = [chartsConfig?.primary_config_id, snapshot.primary_config_id]
  let configId: string | null = null
  for (const id of preferred) {
    if (id && candidates.some((c) => c.id === id)) {
      configId = id
      break
    }
  }
  if (!configId) configId = candidates[0]?.id ?? null

  const gradeMetric =
    snapshot.grade_metric && snapshot.grade_metric.startsWith(metric)
      ? snapshot.grade_metric
      : null
  return { metric, configId, gradeMetric }
}

/** Visible configs that scored `metric`, in snapshot order (selector options). */
export function configsForMetric(
  visibleConfigs: ReportConfigRef[],
  metric: string | null,
): ReportConfigRef[] {
  if (!metric) return []
  return visibleConfigs.filter((c) => c.metric === metric)
}

export interface RankedRow {
  rank: number
  subject: ReportSubject
  config_id: string
  metrics: Record<string, ReportMetricStats>
  /** Stats of the ranking metric (always present on a ranked row). */
  primary: ReportMetricStats
}

/**
 * Rows of `kind` under `configId` that carry `metric`, sorted DESC by mean
 * (ties: larger n first, then label), with ranks assigned from that order.
 */
export function rankSeries(
  series: ReportSeriesRow[],
  configId: string | null,
  metric: string | null,
  kind: ReportSubject['kind'],
  hiddenSubjects: string[] = [],
): RankedRow[] {
  if (!configId || !metric) return []
  const hidden = new Set(hiddenSubjects)
  const rows = series.filter(
    (row) =>
      row.config_id === configId &&
      row.subject.kind === kind &&
      !hidden.has(row.subject.id) &&
      row.metrics[metric] !== undefined,
  )
  const sorted = [...rows].sort((a, b) => {
    const sa = a.metrics[metric]
    const sb = b.metrics[metric]
    if (sb.mean !== sa.mean) return sb.mean - sa.mean
    if (sb.n !== sa.n) return sb.n - sa.n
    return a.subject.label.localeCompare(b.subject.label)
  })
  return sorted.map((row, index) => ({
    rank: index + 1,
    subject: row.subject,
    config_id: row.config_id,
    metrics: row.metrics,
    primary: row.metrics[metric],
  }))
}

/**
 * Additional metric columns for a table: every metric key present on the rows
 * except the primary, the grade companion and hidden companions, filtered by
 * `visible_metrics` when the editor set one.
 */
export function otherMetricColumns(
  rows: Array<Pick<RankedRow, 'metrics'>>,
  primaryMetric: string | null,
  gradeMetric: string | null,
  visibleMetrics?: string[],
): string[] {
  const seen = new Set<string>()
  const columns: string[] = []
  for (const row of rows) {
    for (const key of Object.keys(row.metrics)) {
      if (seen.has(key)) continue
      seen.add(key)
      if (key === primaryMetric || key === gradeMetric) continue
      if (isHiddenMetricKey(key)) continue
      if (Array.isArray(visibleMetrics) && visibleMetrics.length > 0 && !visibleMetrics.includes(key)) {
        continue
      }
      columns.push(key)
    }
  }
  return columns
}

/** The distribution for (configId, metric), or null when the snapshot has none. */
export function distributionFor(
  snapshot: ReportSnapshot,
  configId: string | null,
  metric: string | null,
): ReportDistribution | null {
  if (!configId || !metric) return null
  return (
    snapshot.distributions.find(
      (d) => d.config_id === configId && d.metric === metric,
    ) ?? null
  )
}

export interface PercentBin {
  bin: number
  label: string
  model: number
  human: number
  modelPct: number
  humanPct: number
}

/** Bin label: integer scales show the bin value, continuous scales the range. */
export function binLabel(
  bins: number[],
  index: number,
  scale: ReportMetricScale,
): string {
  const lower = bins[index]
  if (scale === '0-18') return String(lower)
  const upper = index + 1 < bins.length ? bins[index + 1] : scaleUpper(scale, bins)
  if (scale === '0-1') return `${Math.round(lower * 100)}–${Math.round(upper * 100)} %`
  return `${trim(lower)}–${trim(upper)}`
}

function scaleUpper(scale: ReportMetricScale, bins: number[]): number {
  if (scale === '0-1') return 1
  if (scale === '0-100') return 100
  if (scale === '0-18') return 18
  const last = bins[bins.length - 1] ?? 0
  const step = bins.length > 1 ? last - bins[bins.length - 2] : 1
  return last + step
}

function trim(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2)
}

/**
 * Per-bin counts for both kinds plus each kind's share of its own total, so
 * groups of different size compare on one axis.
 */
export function toPercentSeries(distribution: ReportDistribution): PercentBin[] {
  const { bins, by_kind, scale } = distribution
  const modelTotal = by_kind.model.reduce((a, b) => a + b, 0)
  const humanTotal = by_kind.human.reduce((a, b) => a + b, 0)
  const pct = (count: number, total: number) =>
    total > 0 ? Math.round((count / total) * 1000) / 10 : 0
  return bins.map((bin, i) => {
    const model = by_kind.model[i] ?? 0
    const human = by_kind.human[i] ?? 0
    return {
      bin,
      label: binLabel(bins, i, scale),
      model,
      human,
      modelPct: pct(model, modelTotal),
      humanPct: pct(human, humanTotal),
    }
  })
}

export interface SubjectDistribution {
  id: string
  label: string
  total: number
  /** Share of this subject's samples per bin (percent). */
  bins: Array<{ bin: number; label: string; count: number; pct: number }>
}

/**
 * Per-subject histograms for the best `limit` ranked rows that have data in
 * `by_subject` (ranking order preserved).
 */
export function topSubjectDistributions(
  rows: RankedRow[],
  distribution: ReportDistribution | null,
  limit = 8,
): SubjectDistribution[] {
  if (!distribution) return []
  const out: SubjectDistribution[] = []
  for (const row of rows) {
    if (out.length >= limit) break
    const counts = distribution.by_subject[row.subject.id]
    if (!counts) continue
    const total = counts.reduce((a, b) => a + b, 0)
    if (total === 0) continue
    out.push({
      id: row.subject.id,
      label: row.subject.label,
      total,
      bins: distribution.bins.map((bin, i) => ({
        bin,
        label: binLabel(distribution.bins, i, distribution.scale),
        count: counts[i] ?? 0,
        pct: Math.round(((counts[i] ?? 0) / total) * 1000) / 10,
      })),
    })
  }
  return out
}
