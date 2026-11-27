'use client'

/**
 * The before-task questionnaire: after the instructions, before the task.
 *
 * While it is owed, a host shows `BeforeTaskQuestionnaireScreen` INSTEAD of
 * the task: no task text, no editor and no exam timer are mounted, so the
 * questionnaire never counts toward a time limit (a timer starts when its
 * host mounts it, which happens only once `phase === 'done'`). In a Safe Exam
 * Browser exam it appears inside the exam window like the task itself.
 *
 * - `BeforeTaskQuestionnaireGate` wraps a host's task view INCLUDING its
 *   timer component. It mounts its children only once the questionnaire is
 *   answered, skipped (when optional) or not due, shows the questionnaire
 *   while it is due and a spinner while it checks.
 * - `useBeforeTaskQuestionnaire(projectId, taskId, { known, disabled })` is
 *   for a host that needs a callback instead: its `phase` is `checking`
 *   (asking the server), `due` (show `BeforeTaskQuestionnaireScreen`) or
 *   `done`, and the host must mount its timer (start-timer) only when
 *   `phase === 'done'`. Read-only views pass `disabled`.
 * - On the server, `before_task_questionnaire_pending` lets the timer route
 *   refuse a start while the questionnaire is owed.
 */

import { ClipboardDocumentListIcon } from '@heroicons/react/24/outline'
import { useCallback, useEffect, useState, type ReactNode } from 'react'

import { Card } from '@/components/shared/Card'
import { useI18n } from '@/contexts/I18nContext'
import {
  questionnairesAPI,
  type ProjectQuestionnaire,
} from '@/lib/api/questionnaires'
import type { AnnotationResult } from '@/lib/labelConfig/dataBinding'

import { QuestionnaireForm } from './QuestionnaireForm'
import { respondToQuestionnaire } from './respond'

export type BeforeTaskPhase = 'checking' | 'due' | 'done'

export interface BeforeTaskQuestionnaireState {
  phase: BeforeTaskPhase
  questionnaire: ProjectQuestionnaire | null
  /** Call after the questionnaire was answered or skipped. */
  markDone: () => void
}

export interface UseBeforeTaskQuestionnaireOptions {
  /**
   * The project's before-task questionnaire as listed by
   * `questionnairesAPI.list` (undefined while that list loads, null when the
   * project has none switched on). Saves a request per task when known.
   */
  known?: ProjectQuestionnaire | null
  /** Never owe one (read-only views). */
  disabled?: boolean
}

export function useBeforeTaskQuestionnaire(
  projectId: string | null | undefined,
  taskId: string | null | undefined,
  { known, disabled = false }: UseBeforeTaskQuestionnaireOptions = {},
): BeforeTaskQuestionnaireState {
  const [state, setState] = useState<{
    key: string | null
    phase: BeforeTaskPhase
    questionnaire: ProjectQuestionnaire | null
  }>({ key: null, phase: 'checking', questionnaire: null })

  const key = projectId && taskId ? `${projectId}:${taskId}` : null
  // A new task starts in 'checking' in the very render that shows it, so a
  // host never mounts the next task's timer before the check has answered.
  const listLoading = known === undefined
  const noneActive = known === null || (known != null && !known.active)
  // Nothing to ask (read-only, or none switched on): done without a request.
  const owesNothing = disabled || noneActive
  const current = owesNothing
    ? { key, phase: 'done' as const, questionnaire: null }
    : state.key === key
      ? state
      : { key, phase: 'checking' as const, questionnaire: null }

  useEffect(() => {
    if (!key || owesNothing || listLoading) return
    let cancelled = false
    const [pid, tid] = key.split(':')
    questionnairesAPI
      .status(pid, 'before_task', { task_id: tid })
      .then((status) => {
        if (cancelled) return
        setState(
          status.due && status.questionnaire
            ? { key, phase: 'due', questionnaire: status.questionnaire }
            : { key, phase: 'done', questionnaire: null },
        )
      })
      .catch(() => {
        // The questionnaire is switched on but the server could not say
        // whether it is owed: ask it (an answer already given comes back as
        // "already answered" and lets the person through).
        if (!cancelled)
          setState({ key, phase: 'due', questionnaire: known ?? null })
      })
    return () => {
      cancelled = true
    }
  }, [key, owesNothing, listLoading, known])

  const markDone = useCallback(() => {
    setState({ key, phase: 'done', questionnaire: null })
  }, [key])

  return {
    phase: current.phase,
    questionnaire: current.questionnaire,
    markDone,
  }
}

export interface BeforeTaskQuestionnaireScreenProps {
  projectId: string
  taskId: string
  questionnaire: ProjectQuestionnaire
  onDone: () => void
  /** Header actions of the host (back, show instructions). */
  actions?: ReactNode
}

export function BeforeTaskQuestionnaireScreen({
  projectId,
  taskId,
  questionnaire,
  onDone,
  actions,
}: BeforeTaskQuestionnaireScreenProps) {
  const { t } = useI18n()
  // The current text, once an editor replaced the one this screen opened with.
  const [replaced, setReplaced] = useState<{
    from: ProjectQuestionnaire
    to: ProjectQuestionnaire
  } | null>(null)
  const shown = replaced?.from === questionnaire ? replaced.to : questionnaire

  const respond = useCallback(
    async (result: AnnotationResult[] | null) => {
      const current = await respondToQuestionnaire(
        projectId,
        'before_task',
        { task_id: taskId },
        shown,
        result,
      )
      if (current) {
        setReplaced({ from: questionnaire, to: current })
        throw new Error(t('questionnaires.answer.versionChanged'))
      }
      onDone()
    },
    [projectId, taskId, shown, questionnaire, onDone, t],
  )
  const handleSubmit = useCallback(
    (result: AnnotationResult[]) => respond(result),
    [respond],
  )
  const handleSkip = useCallback(() => respond(null), [respond])

  return (
    <div
      className="flex min-h-screen flex-col"
      data-testid="before-task-questionnaire"
    >
      {actions && <div className="border-b px-6 py-4">{actions}</div>}
      <div className="flex flex-1 justify-center p-6">
        <Card className="w-full max-w-2xl">
          <div className="space-y-6 p-6 sm:p-8">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-emerald-50 dark:bg-emerald-950">
                <ClipboardDocumentListIcon className="h-6 w-6 text-emerald-600 dark:text-emerald-400" />
              </div>
              <div>
                <h2 className="text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('questionnaires.moments.before_task.promptTitle')}
                </h2>
                <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                  {t('questionnaires.moments.before_task.promptDescription')}
                </p>
              </div>
            </div>
            <QuestionnaireForm
              formKey={`${taskId}:${shown.version}`}
              config={shown.config}
              required={shown.required}
              onSubmit={handleSubmit}
              onSkip={shown.required ? undefined : handleSkip}
            />
          </div>
        </Card>
      </div>
    </div>
  )
}

export interface BeforeTaskQuestionnaireGateProps {
  projectId: string
  taskId: string
  /** The task view, including its timer: rendered only once answered. */
  children: ReactNode
  known?: ProjectQuestionnaire | null
  disabled?: boolean
  actions?: ReactNode
}

export function BeforeTaskQuestionnaireGate({
  projectId,
  taskId,
  children,
  known,
  disabled,
  actions,
}: BeforeTaskQuestionnaireGateProps) {
  const { phase, questionnaire, markDone } = useBeforeTaskQuestionnaire(
    projectId,
    taskId,
    { known, disabled },
  )
  if (phase === 'done') return <>{children}</>
  if (phase === 'due' && questionnaire) {
    return (
      <BeforeTaskQuestionnaireScreen
        projectId={projectId}
        taskId={taskId}
        questionnaire={questionnaire}
        onDone={markDone}
        actions={actions}
      />
    )
  }
  return (
    <div
      className="flex min-h-[40vh] items-center justify-center"
      data-testid="before-task-questionnaire-checking"
    >
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-300 border-t-emerald-500 dark:border-zinc-600 dark:border-t-emerald-400" />
    </div>
  )
}
