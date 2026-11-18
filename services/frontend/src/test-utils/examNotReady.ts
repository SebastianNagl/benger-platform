/**
 * Test fixtures for the 403 `{code: "exam_not_ready"}` a participant's task
 * read gets while an exam is held closed until its grading sheet is checked,
 * and the notice copy each locale shows for it (ExamNotReadyNotice).
 */

/** The error BaseApiClient throws for a non-OK answer. */
export function apiError(
  status: number,
  detail: unknown,
  message = typeof detail === 'string' ? detail : 'refused',
): Error & { response: { status: number; statusText: string; data: unknown } } {
  const error = new Error(message) as Error & {
    response: { status: number; statusText: string; data: unknown }
  }
  error.response = { status, statusText: '', data: { detail } }
  return error
}

export const EXAM_NOT_READY = apiError(
  403,
  {
    code: 'exam_not_ready',
    reason: 'rubric_missing',
    message: 'This exam is not open yet.',
    project_id: 'exam-1',
  },
  'This exam is not open yet.',
)

export const NOTICE = {
  de: {
    title: 'Noch nicht freigegeben',
    description:
      'Diese Klausur ist noch nicht freigegeben, weil ihr Bewertungsbogen noch geprüft wird. Schau später wieder vorbei.',
  },
  en: {
    title: 'Not released yet',
    description:
      'This exam is not released yet because its grading sheet is still being checked. Please come back later.',
  },
  fr: {
    title: 'Pas encore disponible',
    description:
      "Cet examen n'est pas encore disponible, car sa grille d'évaluation est encore en cours de vérification. Revenez plus tard.",
  },
} as const
