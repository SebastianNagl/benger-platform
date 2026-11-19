/**
 * Inter-annotator agreement per control over tasks with two or more
 * annotators (`GET /api/evaluations/projects/{id}/annotator-agreement`,
 * services/shared/annotator_agreement.py). The same shape is frozen into
 * report snapshots as `annotator_agreement`.
 */

import apiClient from '@/lib/api'

export type AgreementScoreType = 'categorical' | 'ordinal' | 'numeric'

/** Agreement of two annotators (by pseudonym) over the tasks both answered. */
export interface AnnotatorPairAgreement {
  annotator_a: string
  annotator_b: string
  n_items: number
  /** Categorical and ordinal controls. */
  cohens_kappa?: number | null
  /** Number controls. */
  pearson_r?: number | null
}

/** Agreement for one control (Label Studio `from_name`). */
export interface ControlAgreement {
  control: string
  /** Control type: choices, rating or number. */
  type: string
  score_type: AgreementScoreType
  /** A choices control where some annotation picked several options. */
  multi_select: boolean
  /** Tasks with two or more answers for this control. */
  n_items: number
  n_annotators: number
  n_annotations: number
  categories: string[]
  fleiss_kappa: number | null
  cohens_kappa_mean: number | null
  percent_agreement: number | null
  pearson_r_mean: number | null
  mean_absolute_deviation: number | null
  /** Pairs with the most shared tasks first, capped by the API. */
  pairs: AnnotatorPairAgreement[]
  pairs_total: number
}

export interface AnnotatorAgreementSummary {
  overlap_task_count: number
  annotator_count: number
  controls: ControlAgreement[]
  /** Controls without a comparable value (free text, spans, ...). */
  unsupported_controls: Array<{ control: string; type: string }>
}

export interface AnnotatorAgreementResponse extends Partial<AnnotatorAgreementSummary> {
  /** False when no task has two annotators. */
  available: boolean
}

export async function getAnnotatorAgreement(
  projectId: string,
): Promise<AnnotatorAgreementResponse> {
  return apiClient.get(
    `/evaluations/projects/${encodeURIComponent(projectId)}/annotator-agreement`,
  )
}

/** True when the summary has at least one scored control. */
export function hasAgreement(
  summary: Partial<AnnotatorAgreementSummary> | null | undefined,
): summary is AnnotatorAgreementSummary {
  return Boolean(summary && summary.controls && summary.controls.length > 0)
}
