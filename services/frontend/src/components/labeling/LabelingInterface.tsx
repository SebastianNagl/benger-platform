/**
 * LabelingInterface component - Label Studio aligned single-task annotation
 *
 * This component provides a keyboard-driven interface for annotating individual
 * tasks, following Label Studio patterns while integrating BenGER's LLM features.
 */

import { PostAnnotationQuestionnaireModal } from '@/components/labeling/PostAnnotationQuestionnaireModal'
import { useAuth } from '@/contexts/AuthContext'
import { useActivityTracker } from '@/hooks/useActivityTracker'
import { selectVariant } from '@/lib/utils/variantHash'
import { logger } from '@/lib/utils/logger'
import { Badge } from '@/components/shared/Badge'
import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { Separator } from '@/components/shared/Separator'
import { useI18n } from '@/contexts/I18nContext'
import { projectsAPI } from '@/lib/api/projects'
import { useProjectStore } from '@/stores/projectStore'
import { AnnotationResult } from '@/types/labelStudio'
import {
  ArrowLeftIcon,
  BookOpenIcon,
  CheckIcon,
  ClockIcon,
  ExclamationTriangleIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline'
import { formatDistanceToNow } from 'date-fns'
import { useRouter, useSearchParams } from 'next/navigation'
import React, { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'react-hot-toast'
import { useSlot } from '@/lib/extensions/slots'
import { DynamicAnnotationInterface } from './DynamicAnnotationInterface'

interface LabelingInterfaceProps {
  projectId: string
}

export function LabelingInterface({ projectId }: LabelingInterfaceProps) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { t } = useI18n()
  const { user, apiClient } = useAuth()
  const TimerSlot = useSlot('TimerIntegration')
  const ImmediateEvalSlot = useSlot('ImmediateEvaluation')
  // Wraps the labeling interface so the Klausurlösung Angabe / Notizen /
  // Gliederung / Loesung input components see a real LegalMarkdownContext
  // (heading sync, modal navigation). Falls back to React.Fragment in
  // community edition where the extended package isn't loaded.
  const LegalMarkdownProvider = useSlot('LegalMarkdownProvider')
  const AnnotationContextWrapper = LegalMarkdownProvider ?? React.Fragment
  const {
    currentProject,
    currentTask,
    currentTaskPosition,
    currentTaskTotal,
    loading,
    getNextTask,
    createAnnotation,
    createAnnotationInternal,
    skipTask,
    fetchProject,
    fetchProjectTasks,
    taskCycle,
    currentTaskIndex,
    setTaskByIndex,
    advanceToNextTask,
    completeCurrentTask,
    labelConfigVersion,
    allTasksCompleted,
    resetAnnotationCompletion,
  } = useProjectStore()

  const [annotations, setAnnotations] = useState<AnnotationResult[]>([])
  const [loadedAnnotations, setLoadedAnnotations] = useState<AnnotationResult[]>([])
  const [startTime, setStartTime] = useState<number>(Date.now())
  const [initializationError, setInitializationError] = useState<string | null>(
    null
  )
  const [showSkipModal, setShowSkipModal] = useState(false)
  const [skipComment, setSkipComment] = useState('')

  const [serverClockOffset, setServerClockOffset] = useState<number>(0)
  const hasSubmittedRef = useRef(false)
  const lastSyncedAnnotationsRef = useRef<string>('[]')

  // Instructions modal state
  const [showInstructionsModal, setShowInstructionsModal] = useState(false)
  const [dontShowAgain, setDontShowAgain] = useState(false)
  const [manualInstructionsOpen, setManualInstructionsOpen] = useState(false)
  const INSTRUCTIONS_DISMISSED_KEY = `benger-instructions-dismissed-${projectId}`

  // Conditional instruction variant (determined by hash of userId + taskId)
  const [selectedVariantId, setSelectedVariantId] = useState<string | null>(null)

  // Strict-timer state machine. The timer endpoints live in extended; in
  // community edition the GET 404s and we stay in 'annotating' (the early
  // returns below are gated on isStrictMode anyway, which requires both
  // strict_timer_enabled and annotation_time_limit_enabled — both extended).
  type StrictTimerPhase = 'loading' | 'pre_start' | 'annotating' | 'time_over'
  // Start in 'loading' so TimerSlot doesn't briefly mount and fire a
  // premature POST /start-timer before the init useEffect can route the
  // user to pre_start. The init effect always resolves this to one of
  // pre_start | annotating | time_over (or stays 'annotating' on error /
  // community edition).
  const [strictTimerPhase, setStrictTimerPhase] = useState<StrictTimerPhase>('loading')
  const pendingTimeOverRef = useRef(false)
  const isStrictMode = !!(
    currentProject?.strict_timer_enabled && currentProject?.annotation_time_limit_enabled
  )
  // Reset phase synchronously during render when the task changes — otherwise
  // the previous task's 'annotating' phase carries through the render that
  // bumps currentTask.id, TimerSlot stays mounted, and its own useEffect
  // fires POST /start-timer for the NEW task before the init effect below
  // can route to pre_start. setState-during-render is the React-blessed way
  // to derive state from props without a render lag.
  const lastSeenTaskIdRef = useRef<string | null>(null)
  if (currentTask?.id && currentTask.id !== lastSeenTaskIdRef.current) {
    lastSeenTaskIdRef.current = currentTask.id
    if (strictTimerPhase !== 'loading') {
      setStrictTimerPhase('loading')
    }
  }

  // Load existing annotations when task changes
  useEffect(() => {
    const loadExistingAnnotations = async () => {
      if (!currentTask?.id) {
        setLoadedAnnotations([])
        return
      }

      try {
        const existingAnnotations = await projectsAPI.getTaskAnnotations(
          currentTask.id.toString()
        )

        if (existingAnnotations && existingAnnotations.length > 0) {
          // Get the most recent annotation's results
          const latestAnnotation = existingAnnotations[0]
          if (latestAnnotation.result && Array.isArray(latestAnnotation.result)) {
            setLoadedAnnotations(latestAnnotation.result)
            logger.debug('Loaded existing annotations for task:', currentTask.id, latestAnnotation.result)
          } else {
            setLoadedAnnotations([])
          }
        } else {
          setLoadedAnnotations([])
        }
      } catch (error) {
        logger.warn('Failed to load existing annotations:', error)
        setLoadedAnnotations([])
      }
    }

    loadExistingAnnotations()
  }, [currentTask?.id])

  // Strict-timer phase init: runs on every task change. Decides whether to
  // show pre_start (block on a Start button), time_over (just auto-submitted),
  // or annotating (normal flow). Mirrors BenGer_old/services/frontend/src/
  // components/labeling/LabelingInterface.tsx:268-345.
  useEffect(() => {
    if (!currentProject || !currentTask) return

    // Auto-submit just fired and advanced us; show the time_over screen
    // before re-initializing for the new task.
    if (pendingTimeOverRef.current) {
      pendingTimeOverRef.current = false
      setStrictTimerPhase('time_over')
      return
    }

    if (!currentProject.annotation_time_limit_enabled) {
      setStrictTimerPhase('annotating')
      return
    }

    let cancelled = false

    const initPhase = async () => {
      setStrictTimerPhase('loading')
      try {
        const status = await apiClient.get(
          `/projects/${currentProject.id}/tasks/${currentTask.id}/timer-status`
        ) as { session: any | null; server_time: string }
        if (cancelled) return

        const serverNow = new Date(status.server_time).getTime()
        setServerClockOffset(serverNow - Date.now())

        if (status.session) {
          if (status.session.completed_at) {
            // already submitted (auto or manual). In strict mode, the user
            // shouldn't be back here — but if they navigate manually, show
            // time_over rather than letting them re-annotate.
            setStrictTimerPhase(isStrictMode ? 'time_over' : 'annotating')
          } else if (status.session.is_expired) {
            // zombie: never auto-submitted (e.g. server-side Celery missed it).
            // Strict mode: send them back to pre_start; the next start_timer
            // call will replace the zombie session.
            setStrictTimerPhase(isStrictMode ? 'pre_start' : 'annotating')
          } else {
            setStrictTimerPhase('annotating')
          }
        } else {
          // No session yet. In strict mode, gate on the Start button so
          // reading the instructions doesn't burn timer seconds.
          setStrictTimerPhase(isStrictMode ? 'pre_start' : 'annotating')
        }
      } catch (err) {
        // 404 = endpoint missing (community edition) — assume non-strict flow.
        // Other errors: don't strand the user; let them annotate.
        if (!cancelled) setStrictTimerPhase('annotating')
      }
    }

    initPhase()

    return () => {
      cancelled = true
    }
  }, [currentTask?.id, currentProject?.id, currentProject?.annotation_time_limit_enabled, isStrictMode, apiClient])

  // Strict-mode pre_start "Start" handler. Just flips the phase; the
  // TimerSlot's own POST /start-timer fires when it mounts, which is
  // gated below on strictTimerPhase === 'annotating'.
  const handleStrictTimerStart = useCallback(() => {
    setStrictTimerPhase('annotating')
  }, [])

  // Post-annotation questionnaire state (Issue #1208)
  const [showQuestionnaireModal, setShowQuestionnaireModal] = useState(false)
  const [questionnaireAnnotationId, setQuestionnaireAnnotationId] = useState<string | null>(null)
  // Last submitted annotation ID (for immediate evaluation slot)
  const [lastSubmittedAnnotationId, setLastSubmittedAnnotationId] = useState<string | null>(null)
  const isQuestionnaireEnabled =
    currentProject?.questionnaire_enabled && currentProject?.questionnaire_config

  // Activity tracker for enhanced timing (Issue #1208)
  const activityTracker = useActivityTracker()

  // localStorage keys for saving current task state (persists through page reload)
  const TASK_POSITION_KEY = `benger_task_position_${projectId}_${user?.id ?? 'anon'}`
  const TASK_ID_KEY = `benger_task_id_${projectId}_${user?.id ?? 'anon'}`

  // Load project and task data when projectId changes
  useEffect(() => {
    const initializeAnnotationInterface = async () => {
      try {
        // Clear any stale state first
        setAnnotations([])
        setInitializationError(null)
        resetAnnotationCompletion() // Reset completion flag from previous sessions

        // Always load fresh data for the new project
        logger.debug(
          `Initializing annotation interface for project ${projectId}`
        )
        await fetchProject(projectId)

        // Check for task parameter in URL (e.g., ?task=2)
        const taskParam = searchParams?.get('task')

        // Also check localStorage for saved task ID and position (persists through page reload)
        const savedTaskId = typeof window !== 'undefined'
          ? localStorage.getItem(TASK_ID_KEY)
          : null
        const savedTaskPosition = typeof window !== 'undefined'
          ? localStorage.getItem(TASK_POSITION_KEY)
          : null

        // URL parameter takes priority, then localStorage
        const targetTaskNumber = taskParam
          ? parseInt(taskParam, 10)
          : (savedTaskPosition ? parseInt(savedTaskPosition, 10) : null)

        if (taskParam || savedTaskId || targetTaskNumber) {
          try {
            // Load tasks and navigate to specific task
            // When restoring from localStorage (not URL param), exclude completed tasks
            const useExcludeFilter = !taskParam
            const tasks = await fetchProjectTasks(projectId, useExcludeFilter)
            if (tasks && tasks.length > 0) {
              let taskIndex = -1

              if (taskParam && targetTaskNumber) {
                // URL param: use position directly (1-based)
                taskIndex = targetTaskNumber - 1
              } else if (savedTaskId) {
                // localStorage: find by task ID (stable across filtered list changes)
                taskIndex = tasks.findIndex(t => t.id === savedTaskId)
                if (taskIndex === -1 && targetTaskNumber) {
                  // Task ID not found (already completed/excluded), fall back to position
                  taskIndex = targetTaskNumber - 1
                }
              } else if (targetTaskNumber) {
                // Fall back to position
                taskIndex = targetTaskNumber - 1
              }

              if (taskIndex >= 0 && taskIndex < tasks.length) {
                logger.debug(
                  `Navigating to task at index ${taskIndex}${savedTaskId && !taskParam ? ` (by ID ${savedTaskId.substring(0, 8)})` : ''}`
                )
                setTaskByIndex(taskIndex)
                if (taskParam) {
                  toast.success(t('annotation.taskLoadedFromUrl', { taskNumber: targetTaskNumber }))
                }
                return
              } else if (taskParam) {
                toast.error(
                  t('annotation.taskNotFound', { taskNumber: targetTaskNumber, maxTasks: tasks.length })
                )
                localStorage.removeItem(TASK_POSITION_KEY)
                localStorage.removeItem(TASK_ID_KEY)
              }
              // If saved ID/position not found, fall through to getNextTask
            }
          } catch (error) {
            console.error('Failed to load specific task:', error)
            if (taskParam) {
              toast.error(t('annotation.errors.failedToLoadTask', { defaultValue: 'Failed to load specific task' }))
            }
          }
        }

        // Fallback to normal task loading
        logger.debug('Loading next available task...')
        const task = await getNextTask(projectId)

        // Handle case where no tasks are available
        if (!task) {
          // Clear stale saved task so re-entry doesn't loop back
          localStorage.removeItem(TASK_ID_KEY)
          localStorage.removeItem(TASK_POSITION_KEY)
          setInitializationError(
            t('annotation.errors.noTasksAvailable', { defaultValue: 'No tasks are available for annotation in this project.' })
          )
          return
        }
      } catch (error) {
        console.error('Annotation interface initialization failed:', error)
        const errorMessage =
          error instanceof Error
            ? error.message
            : 'Failed to initialize annotation interface'

        setInitializationError(errorMessage)
        toast.error(errorMessage)
      }
    }

    initializeAnnotationInterface()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, searchParams]) // Include searchParams to react to URL changes

  // Reset state when task changes
  useEffect(() => {
    setAnnotations([])
    setShowInstructionsModal(false) // Force reset so instructions useEffect can re-trigger
    hasSubmittedRef.current = false
    // Start activity tracking for new task (Issue #1208)
    activityTracker.start()
    setStartTime(Date.now())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentTask?.id])

  // Save task position and ID to localStorage whenever task changes (Issue #1110 - page reload persistence)
  useEffect(() => {
    if (currentTaskPosition && currentTaskPosition > 0) {
      try {
        localStorage.setItem(TASK_POSITION_KEY, currentTaskPosition.toString())
      } catch {
        // Ignore localStorage errors
      }
    }
    if (currentTask?.id) {
      try {
        localStorage.setItem(TASK_ID_KEY, currentTask.id)
      } catch {
        // Ignore localStorage errors
      }
    }
  }, [currentTaskPosition, currentTask?.id, TASK_POSITION_KEY, TASK_ID_KEY])

  // Periodic server draft sync for all projects (every 30s, only when annotations changed)
  useEffect(() => {
    if (!currentProject || !currentTask) return

    // Reset sync state when task changes
    lastSyncedAnnotationsRef.current = '[]'

    const SERVER_DRAFT_SYNC_MS = 30_000

    const syncDraft = async () => {
      const serialized = JSON.stringify(annotations)
      if (serialized === lastSyncedAnnotationsRef.current) return
      if (annotations.length === 0) return
      try {
        await projectsAPI.saveDraft(currentProject.id, currentTask.id, annotations)
        lastSyncedAnnotationsRef.current = serialized
      } catch {
        // Silent failure — draft sync is best-effort
      }
    }

    const interval = setInterval(syncDraft, SERVER_DRAFT_SYNC_MS)

    // Save draft when tab becomes hidden (user switches tabs or is about to close)
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        syncDraft()
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      clearInterval(interval)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [currentProject, currentTask, annotations])

  // Reset state when label configuration changes
  useEffect(() => {
    if (labelConfigVersion > 0) {
      logger.debug(
        'Label configuration changed, reinitializing annotation interface'
      )
      // Clear current annotations
      setAnnotations([])
      // Reset any initialization errors
      setInitializationError(null)
      // Re-fetch current task to ensure fresh data
      if (currentTask && projectId) {
        fetchProjectTasks(projectId, true)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- Intentional: only react to labelConfigVersion changes, currentTask is read-only trigger
  }, [labelConfigVersion, projectId, fetchProjectTasks])
   

  // Auto-redirect when all tasks are completed
  useEffect(() => {
    if (allTasksCompleted) {
      // Reset the flag first to prevent redirect loops
      resetAnnotationCompletion()
      // Clear saved task position/ID since all tasks are done (Issue #1110)
      try {
        localStorage.removeItem(TASK_POSITION_KEY)
        localStorage.removeItem(TASK_ID_KEY)
      } catch {
        // Ignore localStorage errors
      }
      // Redirect to project detail page
      router.push(`/projects/${projectId}`)
    }
  }, [allTasksCompleted, projectId, router, resetAnnotationCompletion, TASK_POSITION_KEY, TASK_ID_KEY])

  // Compute conditional-instruction variant for this user. Bucket on
  // (user, project) — NOT on task — so the assignment is stable for the
  // whole project. Per-task bucketing would re-roll on every task and
  // break the A/B experiment design (each user is expected to stay in
  // exactly one cohort across all tasks).
  useEffect(() => {
    if (!user?.id || !currentProject?.id || !currentProject?.conditional_instructions?.length) {
      setSelectedVariantId(null)
      return
    }
    const variantId = selectVariant(
      user.id,
      currentProject.id,
      currentProject.conditional_instructions as { id: string; weight: number }[]
    )
    setSelectedVariantId(variantId)
  }, [user?.id, currentProject?.id, currentProject?.conditional_instructions])

  // Show instructions modal on first load if enabled and not dismissed
  useEffect(() => {
    const hasConditional = currentProject?.conditional_instructions?.length
    const hasRegular = currentProject?.instructions

    // Conditional instructions always show (experiment protocol)
    // Regular instructions require show_instruction to be enabled
    if (!hasConditional && !currentProject?.show_instruction) return
    if (!hasConditional && !hasRegular) return

    // If always visible, show on every task load
    if (currentProject?.instructions_always_visible) {
      setShowInstructionsModal(true)
      return
    }

    // Conditional instructions always show per-task (no dismiss)
    if (hasConditional) {
      setShowInstructionsModal(true)
      return
    }

    // Check if user dismissed instructions for this project
    try {
      const dismissed = localStorage.getItem(INSTRUCTIONS_DISMISSED_KEY)
      if (!dismissed) {
        setShowInstructionsModal(true)
      }
    } catch {
      // localStorage not available, show modal anyway
      setShowInstructionsModal(true)
    }
  }, [currentProject?.show_instruction, currentProject?.instructions, currentProject?.instructions_always_visible, currentProject?.conditional_instructions, INSTRUCTIONS_DISMISSED_KEY, currentTask?.id])

  // Calculate lead time
  const getLeadTime = useCallback(() => {
    return (Date.now() - startTime) / 1000 // seconds
  }, [startTime])

  // Handle annotation submission
  const handleSubmit = useCallback(async () => {
    if (!currentTask || annotations.length === 0) {
      toast.error(t('annotation.errors.pleaseProvideAnnotation', { defaultValue: 'Please provide an annotation' }))
      return
    }

    try {
      await createAnnotation(currentTask.id, annotations)
      // Next task is loaded automatically by the store
    } catch (error) {
      console.error('Failed to submit annotation:', error)
    }
  }, [currentTask, annotations, createAnnotation])

  // Handle task skip
  const handleSkip = useCallback(async () => {
    if (!currentTask || !currentProject) return

    // If comment is required, show modal
    if (currentProject.require_comment_on_skip) {
      setShowSkipModal(true)
      return
    }

    // Otherwise skip without comment
    try {
      await skipTask()
      // Next task is loaded automatically by the store
    } catch (error) {
      console.error('Failed to skip task:', error)
    }
  }, [currentTask, currentProject, skipTask])

  // Handle skip with comment from modal
  const handleSkipWithComment = useCallback(async () => {
    if (!currentTask) return

    try {
      await skipTask(skipComment)
      setShowSkipModal(false)
      setSkipComment('')
      // Next task is loaded automatically by the store
    } catch (error) {
      console.error('Failed to skip task:', error)
    }
  }, [currentTask, skipTask, skipComment])

  // Handle instructions modal close
  const handleInstructionsModalClose = useCallback(() => {
    if (dontShowAgain) {
      try {
        localStorage.setItem(INSTRUCTIONS_DISMISSED_KEY, 'true')
      } catch {
        // Ignore localStorage errors
      }
    }
    setShowInstructionsModal(false)
    setDontShowAgain(false)
    setManualInstructionsOpen(false)
  }, [dontShowAgain, INSTRUCTIONS_DISMISSED_KEY])

  // Submit questionnaire response to API (Issue #1208)
  const handleQuestionnaireSubmit = useCallback(
    async (
      pId: string,
      tId: string,
      aId: string,
      result: AnnotationResult[]
    ) => {
      await projectsAPI.submitQuestionnaireResponse(pId, tId, aId, result)
    },
    []
  )

  // Proceed after questionnaire: advance to next task (Issue #1208)
  const proceedAfterQuestionnaire = useCallback(async () => {
    setShowQuestionnaireModal(false)
    toast.success(t('annotation.saved', { defaultValue: 'Annotation saved' }))
    completeCurrentTask()
    setQuestionnaireAnnotationId(null)
  }, [
    t,
    completeCurrentTask,
  ])

  // Show initialization error if it occurred
  if (initializationError) {
    return (
      <div className="container mx-auto px-4 py-8">
        <Card className="mx-auto max-w-2xl">
          <div className="py-12 text-center">
            <ExclamationTriangleIcon className="mx-auto mb-4 h-12 w-12 text-red-500" />
            <h2 className="mb-2 text-2xl font-bold text-red-600">
              {t('annotation.errors.initializationError', { defaultValue: 'Initialization Error' })}
            </h2>
            <p className="text-muted-foreground mb-6">{initializationError}</p>
            <div className="space-x-4">
              <Button onClick={() => window.location.reload()}>
                {t('annotation.errors.tryAgain', { defaultValue: 'Try Again' })}
              </Button>
              <Button
                variant="secondary"
                onClick={() => router.push(`/projects/${projectId}`)}
              >
                {t('annotation.backToProject', { defaultValue: 'Back to Project' })}
              </Button>
            </div>
          </div>
        </Card>
      </div>
    )
  }

  if (loading && !currentTask) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="border-primary h-8 w-8 animate-spin rounded-full border-b-2"></div>
      </div>
    )
  }

  if (!currentTask) {
    return (
      <div className="container mx-auto px-4 py-8">
        <Card className="mx-auto max-w-2xl">
          <div className="py-12 text-center">
            <CheckIcon className="mx-auto mb-4 h-12 w-12 text-green-500" />
            <h2 className="mb-2 text-2xl font-bold">{t('annotation.allTasksCompleted', { defaultValue: 'All tasks completed!' })}</h2>
            <p className="text-muted-foreground mb-6">
              {t('annotation.allTasksCompletedDescription', { defaultValue: "You've annotated all available tasks in this project." })}
            </p>
            <Button onClick={() => router.push(`/projects/${projectId}`)}>
              {t('annotation.backToProject', { defaultValue: 'Back to Project' })}
            </Button>
          </div>
        </Card>
      </div>
    )
  }

  // Strict-timer pre-start screen: in strict mode, hold the timer at zero
  // until the user explicitly clicks Start. Mirrors BenGer_old/services/
  // frontend/src/components/labeling/LabelingInterface.tsx:788-850.
  if (isStrictMode && strictTimerPhase === 'pre_start') {
    const conditionalVariants = currentProject?.conditional_instructions as { id: string; content: string; weight: number }[] | undefined
    const variantContent = conditionalVariants?.find(v => v.id === selectedVariantId)?.content
    const minutes = Math.round((currentProject?.annotation_time_limit_seconds || 0) / 60)
    return (
      <div className="bg-background flex min-h-screen flex-col" data-testid="klausur-pre-start">
        <div className="border-b px-6 py-4">
          <Button variant="text" onClick={() => router.push(`/projects/${projectId}`)}>
            <ArrowLeftIcon className="mr-2 h-4 w-4" />
            {t('annotation.backToProject', { defaultValue: 'Back to Project' })}
          </Button>
        </div>
        <div className="flex flex-1 items-center justify-center">
          <Card className="mx-auto max-w-lg text-center">
            <div className="space-y-6 p-8">
              <ClockIcon className="mx-auto h-16 w-16 text-emerald-600" />
              <h2 className="text-2xl font-bold">
                {t('annotation.strictTimer.readyTitle', { defaultValue: 'Ready to Begin' })}
              </h2>
              {variantContent && (
                <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-left dark:border-emerald-800 dark:bg-emerald-950">
                  <p className="text-sm font-medium text-emerald-800 dark:text-emerald-200">
                    {t('annotation.instructions.title', { defaultValue: 'Annotation Instructions' })}
                  </p>
                  <p className="mt-2 whitespace-pre-wrap text-sm text-emerald-700 dark:text-emerald-300">
                    {variantContent}
                  </p>
                </div>
              )}
              <p className="text-muted-foreground">
                {t('annotation.strictTimer.readyDescription', {
                  defaultValue: `You will have ${minutes} minutes to complete this annotation. The timer starts when you click Start and cannot be paused or restarted.`,
                  minutes,
                })}
              </p>
              <p className="text-muted-foreground text-sm">
                {t('annotation.strictTimer.readyWarning', {
                  defaultValue: 'Page refresh will not reset the timer.',
                })}
              </p>
              <Button variant="filled" onClick={handleStrictTimerStart}>
                {t('annotation.strictTimer.startButton', { defaultValue: 'Start' })}
              </Button>
            </div>
          </Card>
        </div>
      </div>
    )
  }

  // Strict-timer time-over screen: shown after the timer expires and the
  // auto-submit fires. Gated on !showQuestionnaireModal so the questionnaire
  // flow takes precedence. Mirrors BenGer_old/.../LabelingInterface.tsx:853-908.
  if (isStrictMode && strictTimerPhase === 'time_over' && !showQuestionnaireModal && !allTasksCompleted) {
    return (
      <div className="bg-background flex min-h-screen flex-col">
        <div className="border-b px-6 py-4">
          <Button variant="text" onClick={() => router.push(`/projects/${projectId}`)}>
            <ArrowLeftIcon className="mr-2 h-4 w-4" />
            {t('annotation.backToProject', { defaultValue: 'Back to Project' })}
          </Button>
        </div>
        <div className="flex flex-1 items-center justify-center">
          <Card className="mx-auto max-w-lg text-center">
            <div className="space-y-6 p-8">
              <ExclamationTriangleIcon className="mx-auto h-16 w-16 text-amber-500" />
              <h2 className="text-2xl font-bold">
                {t('annotation.strictTimer.timeOverTitle', { defaultValue: "Time's Up" })}
              </h2>
              <p className="text-muted-foreground">
                {t('annotation.strictTimer.timeOverDescription', {
                  defaultValue: 'Your time is over. Your work so far has been submitted in its latest form.',
                })}
              </p>
              <div className="flex flex-col gap-3">
                <Button
                  variant="filled"
                  onClick={() => {
                    hasSubmittedRef.current = false
                    setStrictTimerPhase('loading')
                    completeCurrentTask()
                  }}
                >
                  {t('annotation.strictTimer.continueButton', { defaultValue: 'Continue' })}
                </Button>
                <Button variant="outline" onClick={() => router.push(`/projects/${projectId}`)}>
                  {t('annotation.backToProject', { defaultValue: 'Back to Project' })}
                </Button>
              </div>
            </div>
          </Card>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-background flex min-h-screen">
      {/* Main content */}
      <div className="flex flex-1 flex-col">
        {/* Header */}
        <div className="border-b px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Button
                variant="text"
                onClick={() => router.push(`/projects/${projectId}`)}
              >
                <ArrowLeftIcon className="mr-2 h-4 w-4" />
                {t('annotation.backToProject', { defaultValue: 'Back to Project' })}
              </Button>
              <Separator orientation="vertical" className="h-6" />
              <div>
                <h1 className="text-lg font-semibold">
                  {currentProject?.title}
                </h1>
                <p className="text-muted-foreground text-sm">
                  Task {currentTaskPosition || '?'} of{' '}
                  {currentTaskTotal || currentProject?.num_tasks || '?'}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-4">
              {/* Instructions button - allows re-viewing dismissed instructions */}
              {(currentProject?.instructions || currentProject?.conditional_instructions?.length) && (
                <Button
                  variant="text"
                  onClick={() => {
                    setManualInstructionsOpen(true)
                    setShowInstructionsModal(true)
                  }}
                >
                  <BookOpenIcon className="mr-2 h-4 w-4" />
                  {t('annotation.instructions.showInstructions', { defaultValue: 'Instructions' })}
                </Button>
              )}
              {TimerSlot &&
              currentProject?.annotation_time_limit_enabled &&
              strictTimerPhase === 'annotating' ? (
                <TimerSlot
                  project={currentProject}
                  task={currentTask}
                  annotations={annotations}
                  paused={showQuestionnaireModal}
                  onAutoSubmit={async (result: any[]) => {
                    if (hasSubmittedRef.current) return
                    hasSubmittedRef.current = true
                    // Bridge to the next task's init: skip re-init and show
                    // time_over instead — but only when no questionnaire/eval
                    // flow will intercept first.
                    pendingTimeOverRef.current = !isQuestionnaireEnabled
                    await projectsAPI.createAnnotation(currentTask.id, {
                      result,
                      was_cancelled: false,
                      auto_submitted: true,
                      lead_time: currentProject.annotation_time_limit_seconds || 0,
                    } as any)
                    if (isStrictMode) setStrictTimerPhase('time_over')
                  }}
                />
              ) : (
                <div className="text-muted-foreground flex items-center gap-2 text-sm">
                  <ClockIcon className="h-4 w-4" />
                  {formatDistanceToNow(startTime)}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Task content */}
        <div className="flex-1 overflow-auto p-6">
          <div className="mx-auto max-w-4xl space-y-6">
            {/* Dynamic annotation interface - label config is required */}
            {currentProject?.label_config ? (
              <AnnotationContextWrapper>
              <DynamicAnnotationInterface
                labelConfig={currentProject.label_config}
                taskData={currentTask.data || {}}
                taskId={currentTask.id} // Pass task ID for proper state clearing
                initialValues={loadedAnnotations} // Load existing annotations (Issue #1082)
                showSubmitButton={currentProject?.show_submit_button !== false}
                requireConfirmBeforeSubmit={currentProject?.require_confirm_before_submit === true}
                startTime={startTime} // Pass start time for auto-save lead_time tracking
                onChange={(results) => setAnnotations(results)}
                onSubmit={async (results) => {
                  try {
                    if (hasSubmittedRef.current) {
                      toast.error(t('annotation.errors.alreadySubmitted', { defaultValue: 'Annotation already submitted' }))
                      return
                    }
                    // Handle dynamic annotation results
                    setAnnotations(results)

                    const hasQuestionnaire = isQuestionnaireEnabled

                    // Calculate lead_time
                    const leadTime = Math.round(
                      ((Date.now() + serverClockOffset) - startTime) / 1000
                    )

                    // Get activity tracker data (Issue #1208)
                    const timing = activityTracker.getData()

                    // Skip auto-advance when questionnaire modal flow is active
                    const annotation = await createAnnotationInternal(
                      currentTask.id,
                      {
                        result: results,
                        lead_time: leadTime,
                        active_duration_ms: timing.activeMs,
                        focused_duration_ms: timing.focusedMs,
                        tab_switches: timing.tabSwitches,
                        instruction_variant: selectedVariantId || undefined,
                      },
                      !!hasQuestionnaire
                    )

                    // Mark as submitted only after successful API call
                    hasSubmittedRef.current = true

                    // Track annotation ID for immediate evaluation slot
                    if (annotation) {
                      setLastSubmittedAnnotationId(annotation.id)
                    }

                    // Show questionnaire first if enabled (Issue #1208)
                    if (hasQuestionnaire && annotation) {
                      setQuestionnaireAnnotationId(annotation.id)
                      setShowQuestionnaireModal(true)
                      return
                    }

                    // Normal flow - show success toast
                    toast.success(t('annotation.saved', { defaultValue: 'Annotation saved' }))
                  } catch (error) {
                    console.error('Failed to submit annotation:', error)
                    hasSubmittedRef.current = false
                    toast.error(t('annotation.errors.submitFailed', { defaultValue: 'Failed to submit annotation' }))
                  }
                }}
                onSkip={
                  currentProject?.show_skip_button !== false
                    ? handleSkip
                    : undefined
                }
              />
              </AnnotationContextWrapper>
            ) : (
              <Card>
                <div className="p-6">
                  <div className="rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20">
                    <div className="flex items-start gap-3">
                      <ExclamationTriangleIcon className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-600 dark:text-red-400" />
                      <div className="text-sm text-red-800 dark:text-red-200">
                        <p className="font-medium">
                          No label configuration found
                        </p>
                        <p className="mt-1">
                          This project requires a label configuration to define
                          the annotation interface. Please configure the project
                          settings before annotating.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </Card>
            )}

            {/* LLM Responses (if available) */}
            {(currentTask as any).llm_responses &&
              Object.keys((currentTask as any).llm_responses).length > 0 && (
                <Card>
                  <div className="p-6 pb-0">
                    <h3 className="flex items-center gap-2 text-lg font-semibold">
                      <SparklesIcon className="h-5 w-5" />
                      LLM Responses
                    </h3>
                  </div>
                  <div className="space-y-4 p-6">
                    {Object.entries((currentTask as any).llm_responses).map(
                      ([modelId, response]) => (
                        <div key={modelId} className="space-y-2">
                          <div className="flex items-center gap-2">
                            <Badge variant="secondary">{modelId}</Badge>
                          </div>
                          <div className="bg-muted rounded-lg p-3">
                            <p className="text-sm">{String(response)}</p>
                          </div>
                        </div>
                      )
                    )}
                  </div>
                </Card>
              )}
          </div>
        </div>
      </div>

      {/* Skip Comment Modal */}
      {showSkipModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="mx-4 max-w-md rounded-lg bg-white p-6 shadow-xl dark:bg-zinc-900">
            <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
              {t('annotation.interface.skipCommentTitle')}
            </h3>
            <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
              {t('annotation.interface.skipCommentMessage')}
            </p>
            <textarea
              value={skipComment}
              onChange={(e) => setSkipComment(e.target.value)}
              placeholder={t('annotation.interface.skipCommentPlaceholder')}
              className="mt-4 w-full rounded-md border border-zinc-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white"
              rows={4}
            />
            <div className="mt-6 flex justify-end gap-3">
              <Button
                onClick={() => {
                  setShowSkipModal(false)
                  setSkipComment('')
                }}
                variant="outline"
              >
                {t('annotation.interface.cancel')}
              </Button>
              <Button
                onClick={handleSkipWithComment}
                disabled={!skipComment.trim()}
                variant="filled"
              >
                {t('annotation.interface.skip')}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Instructions Modal (shown on first load if enabled and not dismissed) */}
      {showInstructionsModal && (currentProject?.instructions || selectedVariantId) && (() => {
        const conditionalVariants = currentProject?.conditional_instructions as { id: string; content: string; weight: number }[] | undefined
        const variantContent = conditionalVariants?.find(v => v.id === selectedVariantId)?.content
        const isAlwaysVisible = currentProject?.instructions_always_visible

        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
            <div className="mx-4 max-w-2xl rounded-lg bg-white p-6 shadow-xl dark:bg-zinc-900">
              <h3 className="flex items-center gap-2 text-lg font-semibold text-zinc-900 dark:text-white">
                <ExclamationTriangleIcon className="h-5 w-5 text-emerald-600" />
                {t('annotation.instructions.title', { defaultValue: 'Annotation Instructions' })}
              </h3>
              <div className="mt-4 max-h-[60vh] overflow-y-auto">
                <div className="prose prose-sm max-w-none text-zinc-700 dark:prose-invert dark:text-zinc-300">
                  {variantContent && currentProject?.instructions && (
                    <p className="whitespace-pre-wrap">{currentProject.instructions}</p>
                  )}
                  <p className="whitespace-pre-wrap">{variantContent || currentProject?.instructions}</p>
                </div>
              </div>
              {!isAlwaysVisible && !variantContent && !manualInstructionsOpen && (
                <div className="mt-6 border-t border-zinc-200 pt-4 dark:border-zinc-700">
                  <label className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
                    <input
                      type="checkbox"
                      checked={dontShowAgain}
                      onChange={(e) => setDontShowAgain(e.target.checked)}
                      className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                    />
                    {t('annotation.instructions.dontShowAgain', { defaultValue: "Don't show again for this project" })}
                  </label>
                </div>
              )}
              <div className="mt-4 flex justify-end">
                <Button onClick={handleInstructionsModalClose} variant="filled">
                  {manualInstructionsOpen
                    ? t('annotation.instructions.close', { defaultValue: 'Close' })
                    : t('annotation.instructions.startAnnotating', { defaultValue: 'Start Annotating' })}
                </Button>
              </div>
            </div>
          </div>
        )
      })()}

      {/* Post-Annotation Questionnaire Modal (Issue #1208) */}
      {isQuestionnaireEnabled && questionnaireAnnotationId && currentTask && (
        <PostAnnotationQuestionnaireModal
          isOpen={showQuestionnaireModal}
          questionnaireConfig={currentProject!.questionnaire_config!}
          projectId={projectId}
          taskId={currentTask.id}
          annotationId={questionnaireAnnotationId}
          onComplete={proceedAfterQuestionnaire}
          onSubmitResponse={handleQuestionnaireSubmit}
        />
      )}

      {/* Immediate evaluation (extended feature) */}
      {ImmediateEvalSlot && currentProject?.immediate_evaluation_enabled && lastSubmittedAnnotationId && (
        <ImmediateEvalSlot
          isOpen={true}
          onClose={() => setLastSubmittedAnnotationId(null)}
          projectId={projectId}
          taskId={currentTask?.id}
          annotationId={lastSubmittedAnnotationId}
        />
      )}

    </div>
  )
}
