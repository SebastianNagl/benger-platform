'use client'

/**
 * Asks the questionnaire of a moment that follows an action, when one is
 * due for the caller: after a submission is final (`after_submit`) or after
 * a grader saved a Korrektur (`korrektur`). While `open`, it asks the server
 * whether the questionnaire is due for `subject`; if so it shows it in a
 * modal, otherwise it calls `onDone` at once. `onDone` also follows the
 * answer or the skip.
 *
 * Korrektur (for the extension's Korrektur modal, after the grade is
 * saved): `<QuestionnairePrompt trigger="korrektur" projectId={...}
 * subject={{ task_evaluation_id }} open={saved} onDone={...} />`. The
 * answers are the grader's own; the questionnaire shows nothing of the
 * submission or its author.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { useI18n } from '@/contexts/I18nContext'
import {
  questionnairesAPI,
  type ProjectQuestionnaire,
  type QuestionnaireSubject,
  type QuestionnaireTrigger,
} from '@/lib/api/questionnaires'
import type { AnnotationResult } from '@/lib/labelConfig/dataBinding'

import { QuestionnaireDialog } from './QuestionnaireDialog'
import { respondToQuestionnaire } from './respond'

export type QuestionnaireOutcome = 'answered' | 'skipped' | 'not_due'

export interface QuestionnairePromptProps {
  projectId: string
  trigger: Exclude<QuestionnaireTrigger, 'before_task'>
  subject: QuestionnaireSubject
  open: boolean
  onDone: (outcome: QuestionnaireOutcome) => void
}

export function QuestionnairePrompt({
  projectId,
  trigger,
  subject,
  open,
  onDone,
}: QuestionnairePromptProps) {
  const { t } = useI18n()
  // The questionnaire to show, for the subject it was asked for.
  const [asked, setAsked] = useState<{
    subjectKey: string
    questionnaire: ProjectQuestionnaire
  } | null>(null)
  const onDoneRef = useRef(onDone)
  useEffect(() => {
    onDoneRef.current = onDone
  }, [onDone])
  const subjectKey = JSON.stringify(subject)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    questionnairesAPI
      .status(projectId, trigger, JSON.parse(subjectKey))
      .then((status) => {
        if (cancelled) return
        if (status.due && status.questionnaire) {
          setAsked({ subjectKey, questionnaire: status.questionnaire })
        } else {
          onDoneRef.current('not_due')
        }
      })
      .catch(() => {
        // Never strand the person behind a questionnaire the server could
        // not be asked about.
        if (!cancelled) onDoneRef.current('not_due')
      })
    return () => {
      cancelled = true
    }
  }, [open, projectId, trigger, subjectKey])

  const finish = useCallback((outcome: QuestionnaireOutcome) => {
    setAsked(null)
    onDoneRef.current(outcome)
  }, [])

  const questionnaire =
    open && asked?.subjectKey === subjectKey ? asked.questionnaire : null

  const respond = useCallback(
    async (result: AnnotationResult[] | null) => {
      if (!questionnaire) return
      const current = await respondToQuestionnaire(
        projectId,
        trigger,
        subject,
        questionnaire,
        result,
      )
      if (current) {
        setAsked({ subjectKey, questionnaire: current })
        throw new Error(t('questionnaires.answer.versionChanged'))
      }
      finish(result ? 'answered' : 'skipped')
    },
    [projectId, trigger, subject, subjectKey, questionnaire, finish, t],
  )
  const handleSubmit = useCallback(
    (result: AnnotationResult[]) => respond(result),
    [respond],
  )
  const handleSkip = useCallback(() => respond(null), [respond])

  if (!questionnaire) return null
  return (
    <QuestionnaireDialog
      isOpen
      trigger={trigger}
      config={questionnaire.config}
      required={questionnaire.required}
      formKey={String(questionnaire.version)}
      onSubmit={handleSubmit}
      onSkip={questionnaire.required ? undefined : handleSkip}
    />
  )
}
