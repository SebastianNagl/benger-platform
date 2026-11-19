/**
 * Reads behind the variant and request views (CORE 2.71): the variant
 * designs of a project, the units of a design and one unit with its tasks,
 * declared spans and answers (services/api/routers/projects/variant_designs.py),
 * and the request record of one generation trial with its hash check
 * (services/api/routers/runs.py).
 *
 * The unit routes need full read access to the project's task content
 * (ORG_ADMIN or CONTRIBUTOR); others get 403.
 */

import apiClient from '@/lib/api'

const NO_STORE: RequestInit = { cache: 'no-store' }

export interface VariantFactor {
  name: string
  type: string
  role?: string
  varies?: string
  source?: string
  levels?: unknown[]
  baseline?: unknown
  minimum?: number
  maximum?: number
}

export interface VariantDesignRow {
  id: string
  project_id: string
  key: string
  version: number
  status: string
  spec: {
    title?: string
    description?: string
    unit?: { name: string; description?: string }
    factors?: VariantFactor[]
    outcomes?: { name: string; control?: string; per_slot?: boolean }[]
    gold?: { name: string; path: string }[]
    invariance?: { fields?: string[]; free?: string[] }
    slots?: { count?: number; factors?: VariantFactor[] } & Record<
      string,
      unknown
    >
  }
  spec_sha256: string
  content_hash: string | null
  frozen_at: string | null
  task_count?: number
}

export interface CheckSection {
  ok: boolean
  problem_count: number
  problems: Record<string, unknown>[]
  [key: string]: unknown
}

export interface DesignCheckReport {
  report: {
    ok: boolean
    task_count: number
    unit_count: number
    assignments: CheckSection
    balance: CheckSection & { expected_cells_per_unit?: number | null }
    invariance: CheckSection & { checked_pairs?: number }
  }
  content_hash: string
}

export interface VariantUnitSummary {
  unit: string
  task_count: number
}

export interface VariantUnitPage {
  items: VariantUnitSummary[]
  total: number
  limit: number
  offset: number
}

/**
 * One field of a task's data: text the design lets vary inside declared
 * spans, a field that may differ freely, or one that must be the same in
 * every task of the unit.
 */
export interface UnitText {
  path: string
  kind: 'spanned' | 'free' | 'fixed'
  text: string | null
  truncated: boolean
  spans: [number, number][]
}

export interface UnitGeneration {
  id: string
  parent_id: string
  model_id: string
  system_key: string
  structure_key: string | null
  run_index: number
  status: string
  response: string | null
  response_truncated: boolean
  fields: Record<string, unknown>
  parse_status: string | null
  refusal: boolean
  truncated: boolean
  finish_reason: string | null
  retried: boolean
  has_request_record: boolean
  request_sha256: string | null
  /** The hash check the request route reports for this answer. */
  hash_check?: TrialRequestView['hash_check']
  created_at: string | null
}

export interface UnitTask {
  id: string
  inner_id: number | null
  factors: Record<string, unknown>
  /** The items inside one answer with their factors (per-slot designs). */
  slots?: { index: number; factors: Record<string, unknown> }[]
  texts: UnitText[]
  gold: { name: string; path: string; value: unknown }[]
  generations: UnitGeneration[]
  /** Answers beyond the per-task cap were left out. */
  generations_truncated?: boolean
}

export interface UnitView {
  project_id: string
  design: {
    key: string
    version: number
    status: string
    content_hash: string | null
    frozen_at: string | null
    unit_name: string | null
    factors: VariantFactor[]
    invariance: { fields?: string[]; free?: string[] }
  }
  unit: string
  system: string | null
  systems: string[]
  tasks: UnitTask[]
  tasks_truncated: boolean
  check: {
    ok: boolean
    task_count: number
    assignments: CheckSection
    balance: CheckSection
    invariance: CheckSection
  }
}

/** What the provider client sent (`generations.request_record`). */
export interface RequestRecord {
  version?: number
  provider?: string | null
  api?: string | null
  capture?: string | null
  model?: string | null
  messages?: { role?: string; content?: unknown }[]
  response_format?: unknown
  parameters?: Record<string, unknown> | null
  requests?: { body?: Record<string, unknown>; capture?: string }[]
}

/**
 * One trial's request record with the hash check. The fields after
 * `request_sha256` arrived with CORE 2.71 and are optional for older APIs.
 */
export interface TrialRequestView {
  id: string
  run_index: number
  request_record?: RequestRecord | null
  request_sha256?: string | null
  computed_sha256?: string | null
  hash_matches?: boolean | null
  /** The hash check's state; `record_missing` is a hash without its record. */
  hash_check?: 'verified' | 'mismatch' | 'record_missing' | 'no_hash'
  parent_id?: string | null
  task_id?: string | null
  model_id?: string | null
  system_key?: string | null
  structure_key?: string | null
  retried?: boolean
  first_response?: string | null
  first_response_truncated?: boolean
}

const designPath = (projectId: string, key: string) =>
  `/projects/${encodeURIComponent(projectId)}/variant-designs/${encodeURIComponent(key)}`

export const variantViewsAPI = {
  /** The project's variant designs with their task counts. */
  listDesigns: async (projectId: string): Promise<VariantDesignRow[]> => {
    const page = (await apiClient.get(
      `/projects/${encodeURIComponent(projectId)}/variant-designs`,
      NO_STORE,
    )) as { items?: VariantDesignRow[] }
    return page?.items ?? []
  },

  /** The assignment, balance and invariance checks of a design (read only). */
  checkDesign: async (
    projectId: string,
    key: string,
  ): Promise<DesignCheckReport> =>
    apiClient.post(`${designPath(projectId, key)}/check`, {}),

  /** The units of a design in name order, paged. */
  listUnits: async (
    projectId: string,
    key: string,
    limit = 20,
    offset = 0,
  ): Promise<VariantUnitPage> => {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    })
    return apiClient.get(`${designPath(projectId, key)}/units?${params}`)
  },

  /** One unit with its tasks and the answers of `system` (all when null). */
  getUnit: async (
    projectId: string,
    key: string,
    unit: string,
    system?: string | null,
  ): Promise<UnitView> => {
    const query = system ? `?${new URLSearchParams({ system })}` : ''
    return apiClient.get(
      `${designPath(projectId, key)}/units/${encodeURIComponent(unit)}${query}`,
    )
  },

  /**
   * The request record of a trial with its hash check: under its generation
   * run when the run is known, else by the trial id alone.
   */
  getTrialRequest: async (
    trialId: string,
    generationId?: string | null,
  ): Promise<TrialRequestView> =>
    apiClient.get(
      generationId
        ? `/runs/generations/${generationId}/trials/${trialId}/request`
        : `/runs/trials/${encodeURIComponent(trialId)}/request`,
    ),
}
