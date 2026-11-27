/**
 * Sends an answer or a skip of the questionnaire that was shown, with the
 * version it was rendered from.
 */

import {
  questionnairesAPI,
  type ProjectQuestionnaire,
  type QuestionnaireSubject,
  type QuestionnaireTrigger,
} from '@/lib/api/questionnaires'
import type { AnnotationResult } from '@/lib/labelConfig/dataBinding'

/**
 * Why an answer was refused with 409: it was already given (go on), or the
 * questionnaire was changed since it was shown (load the current version
 * and ask again). Null for any other error.
 */
function answerConflict(
  err: any,
): 'already_answered' | 'version_changed' | null {
  if ((err?.response?.status ?? err?.status) !== 409) return null
  return err?.response?.data?.detail?.code === 'questionnaire_version_changed'
    ? 'version_changed'
    : 'already_answered'
}

/**
 * Answer (`result`) or skip (`null`) the questionnaire `shown`. Resolves
 * null once the answer is stored (or was given before), or with the
 * questionnaire now due when an editor replaced the shown version
 * meanwhile: show that one and ask again.
 */
export async function respondToQuestionnaire(
  projectId: string,
  trigger: QuestionnaireTrigger,
  subject: QuestionnaireSubject,
  shown: ProjectQuestionnaire,
  result: AnnotationResult[] | null,
): Promise<ProjectQuestionnaire | null> {
  try {
    if (result) {
      await questionnairesAPI.answer(
        projectId,
        trigger,
        subject,
        result,
        shown.version,
      )
    } else {
      await questionnairesAPI.skip(projectId, trigger, subject, shown.version)
    }
  } catch (err) {
    const conflict = answerConflict(err)
    if (conflict === 'version_changed') {
      const status = await questionnairesAPI.status(
        projectId,
        trigger,
        subject,
      )
      return status.due ? status.questionnaire : null
    }
    if (conflict !== 'already_answered') throw err
  }
  return null
}
