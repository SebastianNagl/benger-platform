/**
 * Project report data contract (shared by the API's report snapshot, the
 * /reports/[id] viewer and the report editor).
 *
 * A report snapshot is computed server-side (SQL aggregation, no row loads)
 * when a report is refreshed or published, and stored in
 * `content.snapshot`. Viewers render the snapshot, never live data, so a
 * published benchmark report is stable and cheap to serve.
 */

/** Metric scale families the viewer knows how to format. */
export type ReportMetricScale = '0-1' | '0-100' | '0-18' | 'raw'

export interface ReportMethod {
  /** Metric id as stored in task_evaluations.metrics (e.g. llm_judge_falloesung). */
  id: string
  /** Human-readable name (metric registry / EvaluationType name). */
  name: string
  /** lexical | semantic | classification | llm_judge | human | derived */
  category: string
  scale: ReportMetricScale
  higher_is_better: boolean
  /** True for values derived from another metric (e.g. *_grade_points, *_passed). */
  derived?: boolean
}

/** One evaluation configuration (metric + judge model) that produced scores. */
export interface ReportConfigRef {
  /** evaluation_config_id as stored on task_evaluations ('' when rows carry none). */
  id: string
  metric: string
  /** Judge model id for llm_judge_* metrics, else null. */
  judge_model: string | null
  /** Judge display name, else null. */
  judge_label: string | null
  /** Config display name from the project's evaluation config, if any. */
  name: string | null
  /** Number of scored samples under this config. */
  n: number
}

export interface ReportSubject {
  /** Model id (generations) or "annotator:<display>" (human submissions). */
  id: string
  kind: 'model' | 'human'
  /** Display name: LLMModel.name for models, pseudonym-rule display for humans. */
  label: string
  /** Provider (models only). */
  provider?: string | null
  /** Custom / BYOM model (models only). Hidden from public snapshots unless public. */
  is_custom?: boolean
}

export interface ReportMetricStats {
  mean: number
  n: number
  std?: number | null
  min?: number | null
  max?: number | null
  /** Share of samples with a "passed" flag, if the metric carries one. */
  pass_rate?: number | null
}

export interface ReportSeriesRow {
  subject: ReportSubject
  /** Which evaluation config these stats come from (judge-swap studies keep judges apart). */
  config_id: string
  /** Per-metric aggregate stats for this subject under that config
   *  (the config's metric plus its derived companions, e.g. *_grade_points). */
  metrics: Record<string, ReportMetricStats>
}

export interface ReportDistribution {
  metric: string
  config_id: string
  scale: ReportMetricScale
  /** Bin lower edges; the last bin is closed on the upper end. */
  bins: number[]
  /** Counts per bin, summed over all subjects of that kind. */
  by_kind: { model: number[]; human: number[] }
  /** Counts per bin per subject id (models and annotators). */
  by_subject: Record<string, number[]>
}

export interface ReportSnapshot {
  /** ISO timestamp of the snapshot computation. */
  generated_at: string
  statistics: {
    task_count: number
    annotation_count: number
    participant_count: number
    model_count: number
    evaluation_count: number
  }
  methods: ReportMethod[]
  configs: ReportConfigRef[]
  /** The metric the tables rank by and the headline histogram uses. */
  primary_metric: string | null
  /** The config the headline ranking/histogram uses (most samples of the primary metric by default). */
  primary_config_id: string | null
  /** Companion metric on the 0-18 grade-point scale, when the primary metric has one. */
  grade_metric: string | null
  series: ReportSeriesRow[]
  distributions: ReportDistribution[]
  participants: Array<{ id: string; label: string; annotation_count: number }>
  models: ReportSubject[]
}

/** Editor-controlled presentation settings, stored in content.sections.evaluation.charts_config. */
export interface ReportChartsConfig {
  visible_metrics?: string[]
  available_views?: string[]
  default_view?: string
  /** Overrides snapshot.primary_metric. */
  primary_metric?: string | null
  /** Overrides snapshot.primary_config_id. */
  primary_config_id?: string | null
  /** Config ids shown in the report (default: all). */
  visible_configs?: string[]
  /** Subject ids (models/annotators) the editor excluded from the report. */
  hidden_subjects?: string[]
  /** Show the humans-vs-models distribution chart. */
  show_distribution?: boolean
  /** Show the per-annotator rows / distribution. */
  show_humans?: boolean
}
