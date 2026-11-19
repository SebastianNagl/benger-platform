/**
 * Code validations (services/api/routers/coding.py): the agreement of one
 * code (a text pattern code, a coder plugin or a judge system) with the
 * human codes of a coding project, stored with the code's identity hash.
 * Analysis runs accept a code measure's validation only for that hash.
 */

import apiClient from '@/lib/api'

export type CodeValidationStatus =
  'pending' | 'running' | 'completed' | 'failed' | string

/** A validation as the listings return it (no metrics). */
export interface CodeValidationSummary {
  id: string
  /** The coding project the validation ran on. */
  project_id: string
  /** The project whose answers the coding project was drawn from. */
  source_project_id: string | null
  name: string
  status: CodeValidationStatus
  control: string
  code_kind: string
  code_ref: string | null
  code_version: string | null
  code_hash: string | null
  n_items: number | null
  n_compared: number | null
  kappa: number | null
  observed_agreement: number | null
  error_message: string | null
  created_at: string | null
  completed_at: string | null
  /** Listings of a project's answers (`of=answers`) only. */
  coding_project_title?: string | null
}

/** Agreement of two label sequences (unweighted Cohen's kappa). */
export interface KappaAgreement {
  n: number
  kappa: number | null
  observed_agreement: number | null
  expected_agreement: number | null
}

/** Precision, recall and F1 of one category, the human reference as truth. */
export interface CategoryAgreement {
  support: number
  predicted: number
  true_positives: number
  precision: number | null
  recall: number | null
  f1: number | null
}

export interface BetweenCoders {
  coders: number | null
  items: number | null
  fleiss_kappa: number | null
  percent_agreement: number | null
}

/** `code_validations.metrics` (analysis.coding.validation_metrics). */
export interface CodeValidationMetrics {
  version?: number
  items: number
  compared: number
  ties: number
  no_human_code: number
  missing_automatic: number
  missing: 'category' | 'exclude' | string
  categories: string[]
  automatic_vs_reference: KappaAgreement & {
    confusion?: Record<string, Record<string, number>>
    per_category?: Record<string, CategoryAgreement>
  }
  automatic_vs_coders?: Record<string, KappaAgreement>
  between_coders?:
    (BetweenCoders & { pairwise?: Record<string, KappaAgreement> }) | null
}

/** One validation with its metrics (`GET /api/code-validations/{id}`). */
export interface CodeValidationDetail extends CodeValidationSummary {
  metrics: CodeValidationMetrics | null
  warnings: string[] | null
}

const NO_STORE: RequestInit = { cache: 'no-store' }

export const codingAPI = {
  /** One validation with its metrics. */
  getValidation: async (validationId: string): Promise<CodeValidationDetail> =>
    apiClient.get(
      `/code-validations/${encodeURIComponent(validationId)}`,
      NO_STORE,
    ),

  /**
   * The validations of a project's answers: those run on the coding
   * projects drawn from it that the caller can open, newest first.
   */
  listAnswerValidations: async (
    projectId: string,
    limit = 50,
    offset = 0,
  ): Promise<{ items: CodeValidationSummary[]; total: number }> => {
    const params = new URLSearchParams({
      of: 'answers',
      limit: String(limit),
      offset: String(offset),
    })
    return apiClient.get(
      `/projects/${encodeURIComponent(projectId)}/code-validations?${params}`,
      NO_STORE,
    )
  },
}
