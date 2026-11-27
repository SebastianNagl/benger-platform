/**
 * Project questionnaires (`routers/projects/questionnaire.py`): one per
 * project and moment, all answers in one store.
 *
 * - `before_task`: after the instructions, before the task text and any exam
 *   timer (the timer starts only once it is answered or skipped).
 * - `after_submit`: right after a submission is final.
 * - `korrektur`: the grader's, after saving a Korrektur (the extension shows
 *   it with `KorrekturQuestionnairePrompt`).
 */

import apiClient from '@/lib/api'
import type { AnnotationResult } from '@/lib/labelConfig/dataBinding'

export type QuestionnaireTrigger = 'before_task' | 'after_submit' | 'korrektur'

export const QUESTIONNAIRE_TRIGGERS: QuestionnaireTrigger[] = [
  'before_task',
  'after_submit',
  'korrektur',
]

export type QuestionnaireFrequency =
  | 'once_per_project'
  | 'once_per_task'
  | 'once_per_submission'

export interface ProjectQuestionnaire {
  trigger: QuestionnaireTrigger
  enabled: boolean
  config: string
  /** False: the whole questionnaire may be skipped (the skip is recorded). */
  required: boolean
  frequency: QuestionnaireFrequency
  /** Config edits so far (0 = never configured). */
  version: number
  /** Switched on and configured: shown at its moment. */
  active: boolean
  allowed_frequencies: QuestionnaireFrequency[]
  updated_at: string | null
}

export interface QuestionnaireUpdate {
  enabled: boolean
  config: string
  required: boolean
  frequency: QuestionnaireFrequency
}

/** What an answer is about (the fields its moment needs). */
export interface QuestionnaireSubject {
  task_id?: string
  annotation_id?: string
  task_evaluation_id?: string
}

export interface QuestionnaireStatus {
  due: boolean
  questionnaire: ProjectQuestionnaire | null
}

export interface QuestionnaireAnswer {
  id: string
  trigger: QuestionnaireTrigger
  questionnaire_version: number | null
  skipped: boolean
  result: AnnotationResult[]
  created_at: string | null
}

const base = (projectId: string) => `/projects/${projectId}/questionnaires`

function query(params: Record<string, string | undefined>): string {
  const entries = Object.entries(params).filter(
    (entry): entry is [string, string] => !!entry[1],
  )
  return entries.length ? `?${new URLSearchParams(entries)}` : ''
}

export const questionnairesAPI = {
  list: async (
    projectId: string,
  ): Promise<{ questionnaires: ProjectQuestionnaire[]; can_edit: boolean }> =>
    apiClient.get(base(projectId), { cache: 'no-store' } as any),

  save: async (
    projectId: string,
    trigger: QuestionnaireTrigger,
    body: QuestionnaireUpdate,
  ): Promise<ProjectQuestionnaire> =>
    apiClient.put(`${base(projectId)}/${trigger}`, body),

  validate: async (
    projectId: string,
    config: string,
  ): Promise<{ valid: boolean; errors: string[] }> =>
    apiClient.post(`${base(projectId)}/validate`, { config }),

  status: async (
    projectId: string,
    trigger: QuestionnaireTrigger,
    subject: QuestionnaireSubject,
  ): Promise<QuestionnaireStatus> =>
    apiClient.get(`${base(projectId)}/${trigger}/status${query({ ...subject })}`, {
      cache: 'no-store',
    } as any),

  /** `version`: the `version` of the questionnaire that was rendered. */
  answer: async (
    projectId: string,
    trigger: QuestionnaireTrigger,
    subject: QuestionnaireSubject,
    result: AnnotationResult[],
    version: number,
  ): Promise<QuestionnaireAnswer> =>
    apiClient.post(`${base(projectId)}/${trigger}/responses`, {
      ...subject,
      result,
      questionnaire_version: version,
    }),

  skip: async (
    projectId: string,
    trigger: QuestionnaireTrigger,
    subject: QuestionnaireSubject,
    version: number,
  ): Promise<QuestionnaireAnswer> =>
    apiClient.post(`${base(projectId)}/${trigger}/responses`, {
      ...subject,
      result: [],
      skipped: true,
      questionnaire_version: version,
    }),

  /** Href of the wide CSV (one row per answer, one column per question). */
  csvUrl: (projectId: string, trigger: QuestionnaireTrigger | 'all' = 'all') =>
    `/api/projects/${projectId}/questionnaire-responses/export.csv${query({ trigger })}`,
}
