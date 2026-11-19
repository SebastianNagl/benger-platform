/**
 * Paths of the result pages. Every result is viewed on /evaluations: metric
 * evaluations and analysis runs are its two result types, and run pages live
 * under it (/evaluations/[id] for an evaluation run,
 * /evaluations/analysis/[runId] for an analysis run). Overlays build their
 * links with these helpers instead of spelling the paths out.
 */

/** Result types of the evaluations page (`type` in its URL). */
export type ResultType = 'metrics' | 'analysis'

/** The `type` URL value of the analysis result type (metrics is the default). */
export const ANALYSIS_TYPE = 'analysis'

/** The result type a `type` URL value selects. */
export function resultTypeOf(value: string | null | undefined): ResultType {
  return value === ANALYSIS_TYPE ? 'analysis' : 'metrics'
}

/** The page of one analysis run. */
export function analysisRunPath(runId: string): string {
  return `/evaluations/analysis/${encodeURIComponent(runId)}`
}

export interface EvaluationsPathOptions {
  projectId?: string | number | null
  /** Result type; metrics (the default) adds nothing to the URL. */
  type?: ResultType | null
  /** Analysis run to select (analysis type only). */
  run?: string | null
  /** Open the start dialog prefilled with this run's spec (analysis only). */
  newRunFrom?: string | null
}

/** The evaluations page for a project, result type and run. */
export function evaluationsPath(options: EvaluationsPathOptions = {}): string {
  const params = new URLSearchParams()
  if (options.projectId !== undefined && options.projectId !== null) {
    params.set('projectId', String(options.projectId))
  }
  if (options.type === 'analysis') {
    params.set('type', ANALYSIS_TYPE)
    if (options.run) params.set('run', options.run)
    if (options.newRunFrom) params.set('newRunFrom', options.newRunFrom)
  }
  const query = params.toString()
  return query ? `/evaluations?${query}` : '/evaluations'
}

const LEGACY_ANALYSIS = /^\/projects\/([^/]+)\/analysis(?:\/([^/]+))?\/?$/

function decodeSegment(segment: string): string {
  try {
    return decodeURIComponent(segment)
  } catch {
    return segment
  }
}

/**
 * Where an old analysis URL now lives, or null for any other path. The
 * analysis pages moved under /evaluations: `/projects/{id}/analysis` (its
 * `?from={runId}` becomes `newRunFrom`) and `/projects/{id}/analysis/{runId}`.
 * The proxy answers these with a permanent redirect, so bookmarks and stored
 * links keep working.
 */
export function legacyAnalysisPath(
  pathname: string,
  search: URLSearchParams,
): string | null {
  const match = LEGACY_ANALYSIS.exec(pathname)
  if (!match) return null
  const [, projectId, runId] = match
  if (runId) return analysisRunPath(decodeSegment(runId))
  return evaluationsPath({
    projectId: decodeSegment(projectId),
    type: 'analysis',
    newRunFrom: search.get('from') || null,
  })
}
