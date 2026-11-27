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
 *   (asking the server), `due` (show `BeforeTaskQuestionnaireScreen`),
 *   `error` (the server could not say, show `BeforeTaskQuestionnaireError`
 *   with `retry`) or `done`, and the host must mount its timer (start-timer)
 *   only when `phase === 'done'`. Read-only views pass `disabled`.
 * - It fails closed: a host whose questionnaire list could not be loaded
 *   passes `known: 'unknown'` and the hook asks the server per task; when
 *   that fails too, the phase is `error`, never `done`.
 * - On the server, `before_task_questionnaire_pending` lets the timer route
 *   refuse a start while the questionnaire is owed (409 with that code). A
 *   timer that gets this answer calls the host's `recheck`, which asks the
 *   server again and shows the questionnaire instead of the task.
 */

import { ClipboardDocumentListIcon } from '@heroicons/react/24/outline'
import { useCallback, useEffect, useState, type ReactNode } from 'react'

import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { useI18n } from '@/contexts/I18nContext'
import {
  questionnairesAPI,
  type ProjectQuestionnaire,
} from '@/lib/api/questionnaires'
import type { AnnotationResult } from '@/lib/labelConfig/dataBinding'

import { QuestionnaireForm } from './QuestionnaireForm'
import { respondToQuestionnaire } from './respond'

export type BeforeTaskPhase = 'checking' | 'due' | 'error' | 'done'

export interface BeforeTaskQuestionnaireState {
  phase: BeforeTaskPhase
  questionnaire: ProjectQuestionnaire | null
  /** Call after the questionnaire was answered or skipped. */
  markDone: () => void
  /** Ask the server again after `error`. */
  retry: () => void
  /**
   * Ask the server again even when the check said nothing is owed or the
   * project's list showed none switched on: for a timer whose start the
   * server refused with `before_task_questionnaire_pending`.
   */
  recheck: () => void
}

export interface UseBeforeTaskQuestionnaireOptions {
  /**
   * The project's before-task questionnaire as listed by
   * `questionnairesAPI.list` (undefined while that list loads, null when the
   * project has none switched on, 'unknown' when the list could not be
   * loaded, so the server is asked per task). Saves a request per task when
   * known.
   */
  known?: ProjectQuestionnaire | null | 'unknown'
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
    /** Bumped by retry and recheck to ask the server again. */
    attempt: number
    /** Set by recheck: ask the server whatever the list said. */
    forced: boolean
  }>({
    key: null,
    phase: 'checking',
    questionnaire: null,
    attempt: 0,
    forced: false,
  })

  const key = projectId && taskId ? `${projectId}:${taskId}` : null
  const own = state.key === key
  const attempt = own ? state.attempt : 0
  const forced = own && state.forced
  // A new task starts in 'checking' in the very render that shows it, so a
  // host never mounts the next task's timer before the check has answered.
  const listLoading = known === undefined && !forced
  const listed = known && known !== 'unknown' ? known : null
  const noneActive =
    !forced && (known === null || (listed != null && !listed.active))
  // Nothing to ask (read-only, or none switched on): done without a request.
  const owesNothing = disabled || noneActive
  const current = owesNothing
    ? { phase: 'done' as const, questionnaire: null }
    : own
      ? state
      : { phase: 'checking' as const, questionnaire: null }

  useEffect(() => {
    if (!key || owesNothing || listLoading) return
    let cancelled = false
    const [pid, tid] = key.split(':')
    const settle = (
      phase: BeforeTaskPhase,
      questionnaire: ProjectQuestionnaire | null,
    ) =>
      setState((s) => ({
        key,
        phase,
        questionnaire,
        attempt: s.key === key ? s.attempt : 0,
        forced: s.key === key && s.forced,
      }))
    questionnairesAPI
      .status(pid, 'before_task', { task_id: tid })
      .then((status) => {
        if (cancelled) return
        if (status.due && status.questionnaire)
          settle('due', status.questionnaire)
        else settle('done', null)
      })
      .catch(() => {
        if (cancelled) return
        // The server could not say whether it is owed. With the
        // questionnaire known, ask it (an answer already given comes back as
        // "already answered" and lets the person through). Without it, fail
        // closed: an error with retry, never the task.
        if (listed) settle('due', listed)
        else settle('error', null)
      })
    return () => {
      cancelled = true
    }
  }, [key, owesNothing, listLoading, listed, attempt])

  const markDone = useCallback(() => {
    setState((s) => ({
      key,
      phase: 'done',
      questionnaire: null,
      attempt: s.key === key ? s.attempt : 0,
      forced: false,
    }))
  }, [key])

  const askAgain = useCallback(
    (force: boolean) =>
      setState((s) => {
        const same = s.key === key
        return {
          key,
          phase: 'checking',
          questionnaire: null,
          attempt: (same ? s.attempt : 0) + 1,
          forced: force || (same && s.forced),
        }
      }),
    [key],
  )
  const retry = useCallback(() => askAgain(false), [askAgain])
  const recheck = useCallback(() => askAgain(true), [askAgain])

  return {
    phase: current.phase,
    questionnaire: current.questionnaire,
    markDone,
    retry,
    recheck,
  }
}

export interface BeforeTaskQuestionnaireErrorProps {
  onRetry: () => void
  /** Header actions of the host (back, show instructions). */
  actions?: ReactNode
}

/**
 * Shown instead of the task when the server could not say whether the
 * before-task questionnaire is owed: the task and its timer stay hidden
 * until a retry succeeds.
 */
export function BeforeTaskQuestionnaireError({
  onRetry,
  actions,
}: BeforeTaskQuestionnaireErrorProps) {
  const { t } = useI18n()
  return (
    <div
      className="flex min-h-screen flex-col"
      data-testid="before-task-questionnaire-error"
    >
      {actions && <div className="border-b px-6 py-4">{actions}</div>}
      <div className="flex flex-1 items-start justify-center p-6">
        <Card className="w-full max-w-2xl">
          <div className="space-y-4 p-6 sm:p-8" role="alert">
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-white">
              {t('questionnaires.moments.before_task.checkErrorTitle')}
            </h2>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              {t('questionnaires.moments.before_task.checkErrorDescription')}
            </p>
            <div className="flex justify-end">
              <Button variant="filled" onClick={onRetry}>
                {t('questionnaires.moments.before_task.checkRetry')}
              </Button>
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
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
      {/* items-start: the card takes the height of its questions, like the
          after-submit dialog, instead of stretching down the screen. */}
      <div className="flex flex-1 items-start justify-center p-6">
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
  known?: ProjectQuestionnaire | null | 'unknown'
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
  const { phase, questionnaire, markDone, retry } = useBeforeTaskQuestionnaire(
    projectId,
    taskId,
    { known, disabled },
  )
  if (phase === 'done') return <>{children}</>
  if (phase === 'error')
    return <BeforeTaskQuestionnaireError onRetry={retry} actions={actions} />
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
