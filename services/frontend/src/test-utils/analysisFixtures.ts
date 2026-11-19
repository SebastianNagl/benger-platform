/**
 * Invented analysis runs and estimates for the analysis results page tests.
 * The numbers have the shapes the engine writes; they come from no study.
 */

import type {
  AnalysisEstimate,
  AnalysisRun,
  AnalysisTost,
} from '@/lib/api/analysis'

export function makeTost(overrides: Partial<AnalysisTost> = {}): AnalysisTost {
  return {
    lower: -3,
    upper: 3,
    level: 0.9,
    ci_lower: -3.32,
    ci_upper: -1.68,
    p_lower: 0.5,
    p_upper: 0.001,
    p_tost: 0.5,
    equivalent: false,
    ...overrides,
  }
}

export function makeEstimate(
  overrides: Partial<AnalysisEstimate> = {},
): AnalysisEstimate {
  return {
    position: 0,
    estimand_id: 'role',
    contrast_id: 'role',
    estimator: 'fe_ols',
    kind: 'linear',
    outcome: 'share_x',
    scope: 'pooled',
    scope_values: {},
    status: 'ok',
    message: null,
    estimate: -2.5,
    std_error: 0.5,
    statistic: -5,
    df: null,
    p_value: 0.01,
    null_value: 0,
    ci_level: 0.95,
    ci_lower: -3.48,
    ci_upper: -1.52,
    equivalent: null,
    tost: null,
    mde: null,
    ratio: null,
    family: null,
    p_adjusted: null,
    adjustments: [],
    n_obs: 12,
    n_clusters: [3],
    k_params: 1,
    conventions: { ssc: 'statsmodels' },
    ...overrides,
  }
}

/** Pooled plus two systems of one contrast with two bound sets, a family. */
export function makeEstimates(): AnalysisEstimate[] {
  const tost = (ci_lower: number, ci_upper: number, eq: boolean) => [
    makeTost({ ci_lower, ci_upper, equivalent: eq }),
    makeTost({ lower: -2, upper: 2, ci_lower, ci_upper, equivalent: false }),
  ]
  return [
    makeEstimate({
      position: 0,
      tost: tost(-3.32, -1.68, false),
      equivalent: false,
      family: 'primary',
      p_adjusted: 0.02,
      adjustments: [
        {
          family: 'primary',
          method: 'holm',
          group: [],
          size: 2,
          p_adjusted: 0.02,
          mde: { power: 0.8, alpha: 0.05, tests: 2, value: 1.6 },
        },
      ],
    }),
    makeEstimate({
      position: 1,
      scope: 'system=sys_a',
      scope_values: { system: 'sys_a' },
      estimate: -6,
      ci_lower: -8,
      ci_upper: -4,
      p_value: 0.0001,
      tost: tost(-7.6, -4.4, false),
      family: 'per_system',
      p_adjusted: 0.0002,
      adjustments: [
        {
          family: 'per_system',
          method: 'holm',
          group: ['role'],
          size: 2,
          p_adjusted: 0.0002,
        },
      ],
    }),
    makeEstimate({
      position: 2,
      scope: 'system=sys_b',
      scope_values: { system: 'sys_b' },
      estimate: 0.4,
      ci_lower: -1,
      ci_upper: 1.8,
      p_value: 0.57,
      tost: tost(-0.8, 1.6, true),
      equivalent: true,
      family: 'per_system',
      p_adjusted: 0.57,
      adjustments: [
        {
          family: 'per_system',
          method: 'holm',
          group: ['role'],
          size: 2,
          p_adjusted: 0.57,
        },
      ],
    }),
    makeEstimate({
      position: 3,
      estimand_id: 'by_system',
      contrast_id: 'did sys_a',
      status: 'error',
      message: "unknown parameter 'x_p:system[sys_a]'",
      estimate: null,
      std_error: null,
      p_value: null,
      ci_lower: null,
      ci_upper: null,
      n_obs: null,
      n_clusters: null,
    }),
  ]
}

export function makeRun(overrides: Partial<AnalysisRun> = {}): AnalysisRun {
  return {
    id: 'run-1',
    project_id: 'project-1',
    name: 'Role swap',
    status: 'completed',
    spec_hash:
      'e8b39e3aff6d9c532c85baca77dc4d16eb615cee9c796bad44437fff55919df4',
    spec_version: 1,
    engine_version: '1.0.0',
    frame_hash:
      '28e684e10d0db24605e1392fbc85bc1f22c5c4e26707e9d9edfed0355b9658fd',
    frame_rows: 288,
    estimates_count: 4,
    error_message: null,
    created_by: 'user-1',
    created_at: '2026-11-19T08:17:57Z',
    started_at: '2026-11-19T08:17:58Z',
    completed_at: '2026-11-19T08:18:00Z',
    spec: { spec_version: 1, name: 'Role swap', inputs: { designs: ['d'] } },
    normalized_spec: {
      spec_version: 1,
      name: 'Role swap',
      inputs: { designs: ['d'] },
      conventions: { ssc: 'statsmodels' },
    },
    frame_sha256:
      'c1226826f4c637564bc9a7b691ca4afb97e209e852d2f695ec63ed19243e7c23',
    frame_bytes: 17265,
    frame_counts: { observations: 288, units: 24 },
    library_versions: { numpy: '2.5.5', scipy: '1.18.1' },
    lockfile_sha256:
      '1338eabf57231587be98d4d7a1bc92594c0ce9d390df67df617242ea96166125',
    seed: null,
    fits: [
      {
        estimand: 'role',
        scope: 'pooled',
        n: 279,
        k: 2,
        rows_dropped_missing: 9,
        n_clusters: [24, 11],
        fe_levels: [72],
        parameters: ['x_p', 'first_x'],
        dropped: [],
        warnings: [],
      },
    ],
    warnings: ['by_system [pooled]: collinear regressors'],
    timings: { fit_s: 0.64, total_s: 1.9 },
    frame_available: true,
    ...overrides,
  }
}
