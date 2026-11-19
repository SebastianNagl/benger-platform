/**
 * Analysis runs of variant experiments (services/api/routers/analysis.py).
 *
 * A run computes the estimands of an analysis spec on a project whose tasks
 * carry `meta.benger_variant`; the engine runs in the workers, the API validates
 * specs, starts runs and reads runs, estimates and the frame snapshot.
 * Reads of a run that is still pending or running bypass the 30 s GET
 * cache so polling sees the status change.
 */

import apiClient from '@/lib/api'

export type AnalysisRunStatus = 'pending' | 'running' | 'completed' | 'failed'

/** Counts of the frame the run was computed on (keys set by the worker). */
export type AnalysisFrameCounts = Record<string, number>

/** One fit of an estimand in one scope, as the worker summarised it. */
export interface AnalysisFit {
  estimand: string
  scope: string
  n?: number
  k?: number
  rank?: number
  rows?: number
  rows_dropped_missing?: number
  n_clusters?: number[]
  fe_levels?: number[]
  parameters?: string[]
  dropped?: string[]
  warnings?: string[]
  error?: string
  [key: string]: unknown
}

export interface AnalysisRunSummary {
  id: string
  project_id: string
  name: string
  status: AnalysisRunStatus
  spec_hash: string
  spec_version: number
  engine_version: string
  frame_hash: string | null
  frame_rows: number | null
  estimates_count: number | null
  error_message: string | null
  created_by: string | null
  created_at: string | null
  started_at: string | null
  completed_at: string | null
}

export interface AnalysisRun extends AnalysisRunSummary {
  spec: Record<string, unknown>
  normalized_spec: Record<string, unknown>
  frame_sha256: string | null
  frame_bytes: number | null
  frame_counts: AnalysisFrameCounts | null
  library_versions: Record<string, string> | null
  lockfile_sha256: string | null
  seed: number | null
  fits: AnalysisFit[] | null
  warnings: string[] | null
  timings: Record<string, number> | null
  frame_available: boolean
}

/** One equivalence test (TOST) of a contrast against one bound set. */
export interface AnalysisTost {
  lower: number
  upper: number
  level: number
  ci_lower: number | null
  ci_upper: number | null
  p_lower: number | null
  p_upper: number | null
  p_tost: number | null
  equivalent: boolean | null
}

export interface AnalysisMde {
  power: number
  alpha: number
  tests: number
  value: number | null
}

/** One family membership of an estimate with its adjusted p-value. */
export interface AnalysisAdjustment {
  family: string
  method: 'holm' | 'bonferroni' | 'bh' | string
  group: string[]
  size: number
  p_adjusted: number | null
  mde?: AnalysisMde
}

export type AnalysisEstimateStatus = 'ok' | 'degenerate' | 'error' | string

export interface AnalysisEstimate {
  /** Row id (full API only): what a finding's `analysis_estimate_id` cites. */
  id?: number
  position: number
  estimand_id: string
  contrast_id: string | null
  estimator: string
  kind: string | null
  outcome: string | null
  scope: string
  scope_values: Record<string, unknown> | null
  status: AnalysisEstimateStatus
  message: string | null
  estimate: number | null
  std_error: number | null
  statistic: number | null
  df: number | null
  p_value: number | null
  null_value: number | null
  ci_level: number | null
  ci_lower: number | null
  ci_upper: number | null
  equivalent: boolean | null
  tost: AnalysisTost[] | null
  mde: AnalysisMde | null
  ratio: Record<string, unknown> | null
  family: string | null
  p_adjusted: number | null
  adjustments: AnalysisAdjustment[] | null
  n_obs: number | null
  n_clusters: number[] | null
  k_params: number | null
  conventions: Record<string, unknown> | null
}

export interface AnalysisSpecValidation {
  valid: true
  normalized_spec: Record<string, unknown>
  spec_hash: string
  engine_version: string
}

export interface AnalysisFrameDownload {
  url: string
  frame_hash: string | null
  frame_sha256: string | null
}

/** Largest estimates page the API serves (MAX_ESTIMATES_PAGE). */
export const ESTIMATES_PAGE_SIZE = 5000

const NO_STORE: RequestInit = { cache: 'no-store' }

const runPath = (runId: string) => `/analysis-runs/${encodeURIComponent(runId)}`

/** Whether the run can still change (the page polls until it cannot). */
export function isRunActive(status: AnalysisRunStatus | string): boolean {
  return status === 'pending' || status === 'running'
}

/**
 * The validation problems of a rejected spec (422 `invalid_analysis_spec`),
 * or null when the error is something else.
 */
export function specErrorsOf(error: unknown): string[] | null {
  const response = (
    error as { response?: { status?: number; data?: unknown } } | null
  )?.response
  if (!response || response.status !== 422) return null
  const detail = (response.data as { detail?: unknown } | null)?.detail
  if (
    detail &&
    typeof detail === 'object' &&
    (detail as { code?: unknown }).code === 'invalid_analysis_spec' &&
    Array.isArray((detail as { errors?: unknown }).errors)
  ) {
    return ((detail as { errors: unknown[] }).errors ?? []).map(String)
  }
  return null
}

/** The HTTP status of a failed API call, if the error carries one. */
export function statusOf(error: unknown): number | undefined {
  return (error as { response?: { status?: number } } | null)?.response?.status
}

export const analysisAPI = {
  /** The project's runs, newest first. */
  listRuns: async (
    projectId: string,
    limit = 50,
    offset = 0,
  ): Promise<{ items: AnalysisRunSummary[]; total: number }> => {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    })
    return apiClient.get(
      `/projects/${encodeURIComponent(projectId)}/analysis-runs?${params}`,
      NO_STORE,
    )
  },

  /** One run with spec, hashes, versions, counts, fits and warnings. */
  getRun: async (runId: string): Promise<AnalysisRun> =>
    apiClient.get(runPath(runId), NO_STORE),

  /** Every estimate of a run in engine order (pages through the API). */
  listEstimates: async (runId: string): Promise<AnalysisEstimate[]> => {
    const all: AnalysisEstimate[] = []
    for (let offset = 0; ; offset += ESTIMATES_PAGE_SIZE) {
      const params = new URLSearchParams({
        limit: String(ESTIMATES_PAGE_SIZE),
        offset: String(offset),
      })
      const page = (await apiClient.get(
        `${runPath(runId)}/estimates?${params}`,
        NO_STORE,
      )) as { items?: AnalysisEstimate[] }
      const items = page?.items ?? []
      all.push(...items)
      if (items.length < ESTIMATES_PAGE_SIZE) return all
    }
  },

  /** A short-lived download URL of the run's frame snapshot (Parquet). */
  getFrameDownload: async (runId: string): Promise<AnalysisFrameDownload> =>
    apiClient.get(`${runPath(runId)}/frame?json=1`, NO_STORE),

  /** Keys of the project's variant designs (for a starting spec). */
  listDesignKeys: async (projectId: string): Promise<string[]> => {
    const page = (await apiClient.get(
      `/projects/${encodeURIComponent(projectId)}/variant-designs`,
      NO_STORE,
    )) as { items?: { key?: unknown }[] }
    return (page?.items ?? [])
      .map((d) => d?.key)
      .filter((k): k is string => typeof k === 'string')
  },

  /** Validate a spec without starting a run. */
  validateSpec: async (spec: unknown): Promise<AnalysisSpecValidation> =>
    apiClient.post('/analysis/specs/validate', { spec }),

  /** Start a run (edit rights on the project); resolves with the new run. */
  startRun: async (
    projectId: string,
    spec: unknown,
    name?: string,
  ): Promise<AnalysisRun> => {
    const body: Record<string, unknown> = { spec }
    if (name && name.trim()) body.name = name.trim()
    return apiClient.post(
      `/projects/${encodeURIComponent(projectId)}/analysis-runs`,
      body,
    )
  },
}
