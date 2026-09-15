import type { UiMode } from '@/hooks/useResolvedUiMode'

/**
 * Deep links for the "new grading on your submission" notifications.
 *
 * Mirrors the backend helper that builds the link in the notification email
 * (services/shared/mailer/notification_links.py), so the bell, the
 * notifications page and the email all open the same place.
 */
export const EVALUATION_RECEIVED_TYPES = [
  'evaluation_received_human',
  'evaluation_received_immediate',
  'evaluation_received_batch',
] as const

export type EvaluationReceivedType = (typeof EVALUATION_RECEIVED_TYPES)[number]

export function isEvaluationReceivedType(
  type: string | null | undefined,
): type is EvaluationReceivedType {
  return (EVALUATION_RECEIVED_TYPES as readonly string[]).includes(type ?? '')
}

/**
 * A student opens an exam in the student shell. Everyone else lands on the
 * project's own task list, where the grading opens per task. Returns null
 * when the notification carries no project.
 */
export function getEvaluationReceivedHref(
  data: Record<string, any> | null | undefined,
  uiMode: UiMode,
): string | null {
  const projectId = data?.project_id
  if (!projectId) return null
  if (uiMode === 'student' && data?.project_kind === 'exam') {
    return `/student/exams/${projectId}`
  }
  return `/projects/${projectId}/my-tasks`
}
