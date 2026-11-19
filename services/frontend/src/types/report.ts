/**
 * Project report data contract (shared by the API's report snapshot, the
 * /reports/[id] viewer and the report editor).
 *
 * A report snapshot is computed server-side (SQL aggregation, no row loads)
 * when a report is refreshed or published, and stored in
 * `content.snapshot`. Viewers render the snapshot, never live data, so a
 * published benchmark report is stable and cheap to serve.
 */

import type { AnnotatorAgreementSummary } from '@/lib/api/agreement'
import type { AnalysisEstimate } from '@/lib/api/analysis'

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

/** A free-form JSON document (manifest, provenance) with its hash; the
 *  content is left out (`truncated`) when it is too large for a report,
 *  and is never served to a reader outside the project. */
export interface ReportFreeJson {
  sha256: string
  content?: unknown
  truncated?: boolean
}

export interface ReportVariantFactor {
  name: string
  type: string | null
  role: string
  source: string
  varies: string
  levels: Array<string | number | boolean> | null
  level_count: number | null
}

export interface ReportVariantDesign {
  key: string
  version: number
  status: 'draft' | 'frozen' | string
  content_hash: string | null
  spec_sha256: string
  frozen_at: string | null
  task_count: number
  unit_count: number
  cell_count: number
  title: string | null
  unit: string | null
  factors: ReportVariantFactor[]
  outcomes: string[]
  declared_cells: number | null
  provenance: ReportFreeJson | null
}

export interface ReportImport {
  format: string | null
  mode: string | null
  completed_at: string | null
  payload_sha256: string | null
  byte_size: number | null
  task_count: number
  /** A repeat of an identical earlier import that wrote nothing. */
  no_op: boolean
  declared_manifest: ReportFreeJson | null
}

export interface ReportDataSection {
  task_count: number
  variant_designs: ReportVariantDesign[]
  imports: ReportImport[]
  import_count: number
  imports_truncated: boolean
}

export interface ReportGenerationRates {
  generations: number
  completed: number
  failed: number
  /** Share of completed generations; null without any. */
  refusal_rate: number | null
  truncation_rate: number | null
  retry_rate: number | null
  /** Share of parsed generations whose parse failed; null when none was parsed. */
  parse_failure_rate: number | null
  /** Share of generations with a stored request record. */
  request_record_share: number | null
}

export interface ReportStructureCount {
  /** Prompt structure key; null for generations without one. */
  key: string | null
  generations: number
}

export interface ReportGenerationModel extends ReportGenerationRates {
  model_id: string
  label: string
  provider: string | null
  tasks: number
  runs_per_task: number | null
  max_runs_per_task: number | null
  parse_attempted: number
  structures: ReportStructureCount[]
}

export interface ReportGenerationSection {
  models: ReportGenerationModel[]
  structures: ReportStructureCount[]
  totals: ReportGenerationRates
}

export interface ReportLikertDimension {
  dimension: string
  description: string | null
  n: number
  mean: number | null
  std: number | null
  /** Ratings per scale point (1..5). */
  distribution: number[]
  by_model: Array<{
    model_id: string
    label: string
    n: number
    mean: number | null
    std: number | null
  }>
}

export interface ReportPreferenceModel {
  model_id: string
  label: string
  comparisons: number
  wins: number
  losses: number
  ties: number
  win_rate: number | null
}

export interface ReportHumanEvaluations {
  likert: {
    evaluator_count: number
    rating_count: number
    scale: number[]
    dimensions: ReportLikertDimension[]
  }
  preference: {
    evaluator_count: number
    comparisons: number
    ties: number
    models: ReportPreferenceModel[]
    pairs: Array<{
      model_a: string
      label_a: string
      model_b: string
      label_b: string
      a_wins: number
      b_wins: number
      ties: number
    }>
  }
}

export interface ReportAnalysisRunRecord {
  id: string
  name: string
  spec_hash: string
  spec_version: number
  engine_version: string
  frame_hash: string | null
  frame_sha256: string | null
  frame_rows: number | null
  estimates_count: number
  library_versions: Record<string, string> | null
  lockfile_sha256: string | null
  seed: number | null
  completed_at: string | null
  /**
   * A hidden model may appear in the run; readers outside the project never
   * get such a run (absent in snapshots taken before it was recorded).
   */
  member_only?: boolean
}

/** One estimate as a report copies it: the engine's fields, no row id. */
export type ReportAnalysisEstimate = Omit<AnalysisEstimate, 'id'>

/** How an Analyses exhibit draws its estimates. */
export type ReportExhibitType = 'forest' | 'table'

/** Which estimates an exhibit shows; an absent or empty list does not
 *  restrict. Systems keep an estimate only when it involves at least one
 *  system and every system it involves is listed, so a pooled estimate
 *  that involves no system is dropped (`exhibitSelects` in
 *  lib/reports/analyses.ts). */
export interface ReportExhibitFilters {
  estimands?: string[]
  contrasts?: string[]
  families?: string[]
  systems?: string[]
}

export interface ReportAnalysisExhibit {
  /** The exhibit's id in content.sections.analyses (its title and caption). */
  id: string
  type: ReportExhibitType
  filters: ReportExhibitFilters
  /** Equivalence bound set a forest draws (index into `tost`), or none. */
  band: number | null
  /** Estimates the filters matched (before a run's truncation). */
  row_count: number
  /** Positions of its estimates in the run's `estimates`. */
  positions: number[]
}

export interface ReportAnalysisRun {
  id: string
  name: string
  spec_hash: string
  spec_version: number
  engine_version: string
  frame_hash: string | null
  frame_sha256: string | null
  frame_rows: number | null
  estimates_count: number
  completed_at: string | null
  warnings: string[]
  /** Multiplicity families of the shown estimates. */
  families: Array<{
    family: string
    method: string | null
    size: number | null
  }>
  /** A private model may appear in it; the public view leaves it out. */
  member_only?: boolean
  /** More estimates were selected than a report keeps per run. */
  truncated: boolean
  /** The union of its exhibits' estimates, in engine order. */
  estimates: ReportAnalysisEstimate[]
  exhibits: ReportAnalysisExhibit[]
}

export type ReportAnalysisOmission =
  'not_found' | 'not_completed' | 'reads_other_projects'

export interface ReportAnalysesSnapshot {
  runs: ReportAnalysisRun[]
  /** Runs the section names but the report cannot show (authors and
   *  project members only). */
  omitted?: Array<{ run_id: string; reason: ReportAnalysisOmission | string }>
}

export interface ReportReproducibility {
  /** Build the snapshot was computed on (not part of snapshot_sha256). */
  platform: { app_version: string | null; core_api_version: string }
  label_config: { version: string | null; sha256: string | null }
  models: Array<{ id: string; provider: string | null; label: string }>
  prompt_structures: Array<{
    key: string | null
    generations: number
    definition_sha256: string | null
  }>
  evaluation_configs: Array<{
    id: string
    metric: string
    name: string | null
    judge_runs: Array<{
      judge_model: string | null
      samples: number
      parameters_sha256: string | null
      /** Absent for a reader outside the project (hash only). */
      parameters?: unknown
    }>
  }>
  variant_designs: Array<{
    key: string
    version: number
    status: string
    content_hash: string | null
    spec_sha256: string
  }>
  imports: Array<{
    payload_sha256: string | null
    completed_at: string | null
    no_op: boolean
  }>
  analysis_runs: ReportAnalysisRunRecord[]
  /** SHA-256 over the canonical snapshot without generated_at and platform. */
  snapshot_sha256: string | null
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
    /** Completed analysis runs; absent in snapshots taken before CORE 2.67. */
    analysis_count?: number
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
  /** Sections added with the generalised report; absent in older snapshots. */
  data?: ReportDataSection
  generation?: ReportGenerationSection
  human_evaluations?: ReportHumanEvaluations
  /** The runs and exhibits of the Analyses section; absent in older snapshots. */
  analyses?: ReportAnalysesSnapshot
  reproducibility?: ReportReproducibility
  /** Inter-annotator agreement per control; null (or absent in snapshots
   *  taken before it existed) when no task has two annotators. */
  annotator_agreement?: AnnotatorAgreementSummary | null
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
