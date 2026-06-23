/**
 * Shared types for the EvaluationResults component family.
 *
 * NOTE on `SampleEvaluationResult`: this is a LOCAL interface whose shape is
 * deliberately DIFFERENT from the `EvaluationResultSummary` exported by
 * `@/lib/api/types.ts` (that one has `id`/`task_id`/`metrics`; this one
 * has `evaluation_id`/`results_by_config`/`progress`). They are not
 * interchangeable. This file was extracted verbatim from
 * `EvaluationResults.tsx` to share the shape between the orchestrator, the
 * `useResultsData` hook, and the `ResultsModal`.
 */

/** Statistics data structure from computeStatistics API */
export interface StatisticsData {
  by_model?: Record<
    string,
    {
      model_name?: string
      metrics: Record<
        string,
        {
          mean: number
          std: number
          se?: number
          ci_lower: number
          ci_upper: number
          n: number
        }
      >
      sample_count: number
    }
  >
}

/** Statistical methods that can be selected for display */
export type StatisticalMethod =
  | 'ci'
  | 'se'
  | 'std'
  | 'ttest'
  | 'bootstrap'
  | 'cohens_d'
  | 'cliffs_delta'
  | 'correlation'

// Data structure for chart visualization
export interface ChartData {
  model_id: string
  model_name?: string
  metrics: Record<string, number>
  samples_evaluated: number
}

export interface SampleEvaluationResult {
  evaluation_id: string
  model_id: string
  status: string
  created_at: string | null
  completed_at: string | null
  samples_evaluated: number
  sample_results_count: number
  error_message: string | null
  evaluation_configs: Array<{
    id: string
    metric: string
    display_name?: string
    metric_type?: string
    metric_parameters?: Record<string, any>
    prediction_fields: string[]
    reference_fields: string[]
    enabled: boolean
  }>
  results_by_config: Record<
    string,
    {
      field_results: Array<{
        combo_key: string
        prediction_field: string
        reference_field: string
        scores: Record<string, number>
      }>
      aggregate_score: number | null
    }
  >
  progress: {
    samples_passed: number
    samples_failed: number
    samples_skipped: number
  }
}

export interface ProjectEvaluationResults {
  project_id: string
  evaluations: SampleEvaluationResult[]
  total_count: number
}

/** Per-task/model data table payload from getProjectResultsByTaskModel. */
export interface TaskModelData {
  evaluation_id: string
  models: string[]
  model_names: Record<string, string>
  tasks: Array<{
    task_id: string
    task_preview: string
    scores: Record<string, number>
    has_annotation?: boolean
    generation_models?: string[]
    annotator_columns?: string[]
  }>
  summary: Record<string, { avg: number; count: number; model_name: string }>
}

/** Generation-result rows shown in the modal's Generation tab. */
export type GenerationData = Array<{
  task_id: string
  model_id: string
  generation_id: string
  status: string
  result?: {
    generated_text?: string
    created_at?: string
    usage_stats?: Record<string, any>
    fields?: Record<string, any>
  }
  generated_at?: string
  generation_time_seconds?: number
  prompt_used?: string
  parameters?: Record<string, any>
  error_message?: string
  structure_key?: string
}>

/** Per-task evaluation rows shown in the modal's Evaluation tab. */
export interface EvaluationDetailData {
  task_id: string
  model_id: string
  results: Array<{
    id: string
    evaluation_id: string
    field_name: string
    answer_type: string
    ground_truth: any
    prediction: any
    metrics: Record<string, any>
    passed: boolean
    confidence_score?: number
    error_message?: string
    processing_time_ms?: number
    created_at?: string
    evaluation_context?: {
      evaluation_type: string
      status: string
      eval_metadata?: Record<string, any>
    }
  }>
  total_count: number
  message?: string
}

/** Annotation rows shown in the modal's Annotation tab. */
export type AnnotationData = Array<{
  id: string
  task_id: number
  completed_by: string
  result: Array<{ value: any; from_name: string; to_name: string; type: string; [key: string]: any }>
  was_cancelled: boolean
  ground_truth: boolean
  lead_time?: number
  created_at: string
  updated_at?: string
  metadata?: Record<string, any>
}>
