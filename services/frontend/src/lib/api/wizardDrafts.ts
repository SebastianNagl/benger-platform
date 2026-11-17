/**
 * Creation-wizard drafts (CORE 2.55): client for
 * `routers/projects/wizard_drafts.py`. A draft is a real project the wizard
 * creates when the user leaves its first step (only when a registered draft
 * policy applies, see `@/lib/extensions/wizardDraft`); it stays private and
 * unlisted until the finish route applies its visibility.
 */

import apiClient from '@/lib/api'

export interface WizardDraftSummary {
  project_id: string
  title: string
  kind: string | null
  icon: string | null
  step_id: string | null
  target_organization_id: string | null
  target_group_id: string | null
  created_at: string | null
  touched_at: string | null
  /** When the daily sweep deletes the draft (30 days after its last change). */
  expires_at: string | null
}

export interface WizardDraft extends WizardDraftSummary {
  client_key: string
  state: Record<string, any> | null
  state_version: number
}

export interface WizardDraftCreate {
  title: string
  description?: string | null
  kind?: string | null
  label_config?: string | null
  icon?: string | null
  target_organization_id?: string | null
  target_group_id?: string | null
  client_key: string
  state?: Record<string, any> | null
  step_id?: string | null
}

export interface WizardDraftSave {
  state?: Record<string, any> | null
  step_id?: string | null
  if_version: number
  target_organization_id?: string | null
  target_group_id?: string | null
}

export interface WizardDraftFinish {
  client_key: string
  visibility: 'private' | 'organization' | 'public'
  public_role?: 'ANNOTATOR' | 'CONTRIBUTOR' | null
  organization_attachments?: {
    organization_id: string
    group_id: string | null
  }[]
}

export interface WizardDraftSheet {
  id: string
  status: string
  review_state: string | null
}

export interface WizardDraftTask {
  id: string
  inner_id: number | null
  /** The wizard row the task was imported from (0-based), if any. */
  row_index: number | null
  row_hash: string | null
  /** Sheets that are not archived. */
  sheets: WizardDraftSheet[]
  /** Rubric generations still running for the task. */
  generating: number
}

/** The coded detail of a failed draft request, if it carries one. */
export function wizardDraftErrorCode(error: unknown): string | null {
  const detail = (error as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail
  if (detail && typeof detail === 'object' && 'code' in detail) {
    const code = (detail as { code?: unknown }).code
    return typeof code === 'string' ? code : null
  }
  return null
}

const draftUrl = (projectId: string) => `/projects/${projectId}/wizard-draft`

export const wizardDraftsAPI = {
  create: async (body: WizardDraftCreate): Promise<WizardDraft> =>
    apiClient.post('/projects/wizard-drafts', body),

  /** The caller's unfinished drafts, most recently changed first. */
  list: async (): Promise<WizardDraftSummary[]> => {
    apiClient.invalidateCache('/projects/wizard-drafts')
    const res = await apiClient.get('/projects/wizard-drafts')
    return (res?.items as WizardDraftSummary[] | undefined) ?? []
  },

  get: async (projectId: string): Promise<WizardDraft> => {
    apiClient.invalidateCache(draftUrl(projectId))
    return apiClient.get(draftUrl(projectId))
  },

  /** 409 `draft_version_conflict` when another tab saved in between. */
  save: async (
    projectId: string,
    body: WizardDraftSave,
  ): Promise<WizardDraft> => apiClient.put(draftUrl(projectId), body),

  /** Applies the visibility; resolves with the finished project. */
  finish: async (
    projectId: string,
    body: WizardDraftFinish,
  ): Promise<{ id: string }> => {
    const project = await apiClient.post(`${draftUrl(projectId)}/finish`, body)
    apiClient.invalidateCache('/projects')
    return project
  },

  discard: async (projectId: string): Promise<void> => {
    await apiClient.delete(draftUrl(projectId))
    apiClient.invalidateCache('/projects/wizard-drafts')
  },

  tasks: async (projectId: string): Promise<WizardDraftTask[]> => {
    apiClient.invalidateCache(`${draftUrl(projectId)}/tasks`)
    const res = await apiClient.get(`${draftUrl(projectId)}/tasks`)
    return (res?.items as WizardDraftTask[] | undefined) ?? []
  },

  /** Replace a changed row's data in place; its sheets are archived. */
  replaceTask: async (
    projectId: string,
    taskId: string,
    data: Record<string, unknown>,
    rowHash: string,
  ): Promise<{ id: string; archived_sheet_ids: string[] }> =>
    apiClient.put(`${draftUrl(projectId)}/tasks/${taskId}`, {
      data,
      row_hash: rowHash,
    }),
}

export default wizardDraftsAPI
