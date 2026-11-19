/**
 * Variant designs of a project (services/api/routers/projects/
 * variant_designs.py): the declared design of a variant experiment, its
 * checks (assignments, balance, span invariance), the freeze that records
 * the content hash, and the import of an exported design document.
 *
 * Reading needs the project's full-data tier; check is a read, import and
 * freeze need edit rights. Refusals carry `{detail: {code, message,
 * problems?, report?}}`.
 */

import apiClient from '@/lib/api'

export type VariantDesignStatus = 'draft' | 'frozen'

export interface VariantDesign {
  id: string
  project_id: string
  key: string
  version: number
  status: VariantDesignStatus | string
  spec: Record<string, unknown>
  spec_sha256: string
  content_hash: string | null
  frozen_at: string | null
  frozen_by: string | null
  provenance: Record<string, unknown> | null
  created_by: string | null
  created_at: string | null
  updated_at: string | null
  /** Tasks naming the design (list and detail reads). */
  task_count?: number
}

export interface VariantDesignProblem {
  kind?: string
  message: string
  [key: string]: unknown
}

/** One section of a check report. */
export interface VariantCheckSection {
  ok: boolean
  problem_count: number
  problems: VariantDesignProblem[]
  [key: string]: unknown
}

export interface VariantDesignReport {
  design: string
  task_count: number
  unit_count: number
  assignments: VariantCheckSection
  balance: VariantCheckSection & { expected_cells_per_unit?: number | null }
  invariance: VariantCheckSection & { checked_pairs?: number }
  ok: boolean
}

export interface VariantDesignCheck {
  report: VariantDesignReport
  /** The hash a freeze would record now. */
  content_hash: string
}

export interface VariantDesignFreeze {
  design: VariantDesign
  report: VariantDesignReport
}

export interface VariantDesignRefusal {
  status: number
  code: string
  message: string
  problems: VariantDesignProblem[]
  report: VariantDesignReport | null
}

const NO_STORE: RequestInit = { cache: 'no-store' }

const base = (projectId: string) =>
  `/projects/${encodeURIComponent(projectId)}/variant-designs`

/** The refusal of a variant-design call, or null for other errors. */
export function variantDesignRefusalOf(
  error: unknown,
): VariantDesignRefusal | null {
  const response = (
    error as { response?: { status?: number; data?: unknown } } | null
  )?.response
  const detail = (response?.data as { detail?: unknown } | null)?.detail
  if (!response?.status || !detail || typeof detail !== 'object') return null
  const d = detail as Record<string, unknown>
  if (typeof d.code !== 'string') return null
  return {
    status: response.status,
    code: d.code,
    message: typeof d.message === 'string' ? d.message : d.code,
    problems: Array.isArray(d.problems)
      ? (d.problems as VariantDesignProblem[])
      : [],
    report:
      d.report && typeof d.report === 'object'
        ? (d.report as VariantDesignReport)
        : null,
  }
}

export const variantDesignsAPI = {
  /** The project's designs with their task counts, by key. */
  list: async (projectId: string): Promise<VariantDesign[]> => {
    const page = (await apiClient.get(base(projectId), NO_STORE)) as {
      items?: VariantDesign[]
    }
    return page?.items ?? []
  },

  /** Run every check without changing anything. */
  check: async (projectId: string, key: string): Promise<VariantDesignCheck> =>
    apiClient.post(`${base(projectId)}/${encodeURIComponent(key)}/check`, {}),

  /** Freeze a draft whose checks pass (409 with the report otherwise). */
  freeze: async (
    projectId: string,
    key: string,
  ): Promise<VariantDesignFreeze> =>
    apiClient.post(`${base(projectId)}/${encodeURIComponent(key)}/freeze`, {}),

  /** Create a draft from an export document (`GET .../export`). */
  importDocument: async (
    projectId: string,
    document: unknown,
  ): Promise<VariantDesign> =>
    apiClient.post(`${base(projectId)}/import`, document),
}
