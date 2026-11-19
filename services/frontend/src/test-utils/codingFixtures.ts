/**
 * Synthetic code validations for tests. VALIDATION_METRICS is the output of
 * `analysis.coding.validation_metrics` for ten coded items (seven agree, one
 * automatic P against a human D, one missing automatic code, one tie of two
 * coders), the same items services/api/tests/integration/
 * test_report_code_validations.py stores.
 */

import type { AnalysisCodeRecord } from '@/lib/api/analysis'
import type {
  CodeValidationDetail,
  CodeValidationMetrics,
  CodeValidationSummary,
} from '@/lib/api/coding'
import type { ReportCodeValidation } from '@/types/report'

export const VALIDATION_METRICS: CodeValidationMetrics = {
  version: 1,
  items: 10,
  compared: 9,
  ties: 1,
  no_human_code: 0,
  missing_automatic: 1,
  missing: 'category',
  categories: ['(missing)', 'D', 'P'],
  automatic_vs_reference: {
    n: 9,
    kappa: 0.5909090909090909,
    observed_agreement: 0.7777777777777778,
    expected_agreement: 0.45679012345679015,
    confusion: {
      '(missing)': { '(missing)': 0, D: 0, P: 0 },
      D: { '(missing)': 0, D: 3, P: 1 },
      P: { '(missing)': 1, D: 0, P: 4 },
    },
    per_category: {
      '(missing)': {
        support: 0,
        predicted: 1,
        true_positives: 0,
        precision: 0,
        recall: null,
        f1: null,
      },
      D: {
        support: 4,
        predicted: 3,
        true_positives: 3,
        precision: 1,
        recall: 0.75,
        f1: 0.8571428571428571,
      },
      P: {
        support: 5,
        predicted: 5,
        true_positives: 4,
        precision: 0.8,
        recall: 0.8,
        f1: 0.8000000000000002,
      },
    },
  },
  automatic_vs_coders: {
    u1: {
      n: 10,
      kappa: 0.6153846153846155,
      observed_agreement: 0.8,
      expected_agreement: 0.48,
    },
  },
  between_coders: {
    coders: 2,
    items: 1,
    fleiss_kappa: -1,
    percent_agreement: 0,
  },
}

export const PATTERN_HASH = 'e'.repeat(64)

export function makeValidationSummary(
  overrides: Partial<CodeValidationSummary> = {},
): CodeValidationSummary {
  return {
    id: 'val-1',
    project_id: 'coding-1',
    source_project_id: 'project-1',
    name: 'blame pattern',
    status: 'completed',
    control: 'side',
    code_kind: 'text_pattern',
    code_ref: 'blame@1:claimant',
    code_version: '1',
    code_hash: PATTERN_HASH,
    n_items: 10,
    n_compared: 9,
    kappa: VALIDATION_METRICS.automatic_vs_reference.kappa,
    observed_agreement:
      VALIDATION_METRICS.automatic_vs_reference.observed_agreement,
    error_message: null,
    created_at: '2026-11-02T09:00:00Z',
    completed_at: '2026-11-02T09:01:00Z',
    coding_project_title: 'Coding: side',
    ...overrides,
  }
}

export function makeValidationDetail(
  overrides: Partial<CodeValidationDetail> = {},
): CodeValidationDetail {
  return {
    ...makeValidationSummary(),
    metrics: VALIDATION_METRICS,
    warnings: [],
    ...overrides,
  }
}

/** A run's code record that accepted `makeValidationSummary()`. */
export function makeCodeRecord(
  overrides: Partial<AnalysisCodeRecord> = {},
): AnalysisCodeRecord {
  return {
    measure: 'blames_claimant',
    kind: 'text_pattern',
    ref: 'blame@1:claimant',
    version: '1',
    hash: PATTERN_HASH,
    missing: 1,
    rows: 10,
    confirmatory_estimands: ['blame_effect'],
    validation: {
      id: 'val-1',
      coding_project_id: 'coding-1',
      control: 'side',
      kappa: VALIDATION_METRICS.automatic_vs_reference.kappa,
      observed_agreement:
        VALIDATION_METRICS.automatic_vs_reference.observed_agreement,
      compared: 9,
      completed_at: '2026-11-02T09:01:00Z',
    },
    ...overrides,
  }
}

/** The snapshot entry of `makeValidationDetail()` read by `runIds`. */
export function makeReportValidation(
  overrides: Partial<ReportCodeValidation> = {},
): ReportCodeValidation {
  const main = VALIDATION_METRICS.automatic_vs_reference
  return {
    id: 'val-1',
    name: 'blame pattern',
    control: 'side',
    code_kind: 'text_pattern',
    code_ref: 'blame@1:claimant',
    code_version: '1',
    code_hash: PATTERN_HASH,
    kappa: main.kappa,
    observed_agreement: main.observed_agreement,
    compared: 9,
    completed_at: '2026-11-02T09:01:00Z',
    coding_version: 1,
    detail: true,
    agreement: {
      n: main.n,
      kappa: main.kappa,
      observed_agreement: main.observed_agreement,
      expected_agreement: main.expected_agreement,
    },
    counts: {
      items: 10,
      compared: 9,
      ties: 1,
      no_human_code: 0,
      missing_automatic: 1,
      missing: 'category',
    },
    categories: VALIDATION_METRICS.categories,
    per_category: main.per_category,
    confusion: main.confusion,
    between_coders: {
      coders: 2,
      items: 1,
      fleiss_kappa: -1,
      percent_agreement: 0,
    },
    used_by: [{ run_id: 'run-1', measure: 'blames_claimant' }],
    member_only: false,
    ...overrides,
  }
}
