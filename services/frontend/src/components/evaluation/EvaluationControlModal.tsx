'use client'

import { Button } from '@/components/shared/Button'
import { CostEstimatePanel } from '@/components/shared/CostEstimatePanel'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { apiClient } from '@/lib/api/client'
import { Dialog, Transition } from '@headlessui/react'
import { PlayIcon, XMarkIcon } from '@heroicons/react/24/outline'
import { Fragment, useEffect, useMemo, useState } from 'react'

interface EvaluationConfigInput {
  id: string
  metric: string
  display_name?: string
  prediction_fields: string[]
  reference_fields: string[]
  metric_parameters?: Record<string, any>
  enabled?: boolean
}

/** Scope payload handed to `onRunWithMode` so callback-mode parents can
 *  dispatch a narrowed run instead of a full sweep. Mirrors the shape the
 *  modal sends in its built-in submit path (`/evaluations/run` request body
 *  fields). All fields are optional: a parent that ignores them keeps the
 *  pre-scope behaviour, and the modal omits filters when the user hasn't
 *  narrowed (e.g. all metrics still selected). */
export interface EvaluationRunScope {
  /** User-narrowed config list. Filtered by selected metrics; each entry has
   *  `enabled: true` so the backend treats them as a fresh enabled set. */
  evaluationConfigs?: Array<EvaluationConfigInput & { enabled: true }>
  /** Undefined when the user hasn't deselected any model — parent should
   *  treat that as "no filter" and keep today's full-sweep behaviour. */
  modelIds?: string[]
  /** Same semantics as `modelIds` but for annotation-side judges. */
  annotatorUserIds?: string[]
}

interface EvaluationControlModalProps {
  isOpen: boolean
  projectId?: string
  evaluationConfigs?: EvaluationConfigInput[]
  /** Number of configs to display when using callback mode */
  configCount?: number
  onClose: () => void
  onSuccess?: () => void
  /** Callback-mode dispatch. Receives `forceRerun` and the user-narrowed
   *  scope so the parent can forward both to its own `runEvaluation` call.
   *  Parents that pre-date the scope arg simply ignore it — their behaviour
   *  is unchanged for unfiltered runs. */
  onRunWithMode?: (forceRerun: boolean, scope?: EvaluationRunScope) => Promise<void>
}

interface ScopeModel {
  model_id: string
  model_name: string
  provider: string
}

interface ScopeAnnotator {
  user_id: string
  display_name: string
}

export function EvaluationControlModal({
  isOpen,
  projectId,
  evaluationConfigs,
  configCount,
  onClose,
  onSuccess,
  onRunWithMode,
}: EvaluationControlModalProps) {
  const { addToast } = useToast()
  const { t } = useI18n()
  const [mode, setMode] = useState<'all' | 'missing'>('missing')
  const [loading, setLoading] = useState(false)

  // Scope state (issue #69). Each list is the user's CURRENT selection;
  // the available* lists are populated from /evaluated-models on open.
  // Defaults to all-selected so today's full-sweep behavior is preserved
  // when the user just hits Run without touching anything.
  const [availableModels, setAvailableModels] = useState<ScopeModel[]>([])
  const [availableAnnotators, setAvailableAnnotators] = useState<ScopeAnnotator[]>([])
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>([])
  const [selectedModels, setSelectedModels] = useState<string[]>([])
  const [selectedAnnotators, setSelectedAnnotators] = useState<string[]>([])
  const [scopeLoading, setScopeLoading] = useState(false)

  const allConfigs = evaluationConfigs ?? []
  const enabledConfigs = useMemo(
    () => allConfigs.filter(c => c.enabled !== false),
    [allConfigs],
  )
  const displayConfigCount = configCount ?? enabledConfigs.length

  // Derive judge models + max runs across SELECTED llm_judge_* metrics for
  // the inline cost-preview panel. Recomputes when the metric selection
  // changes so the dollar number tracks the chosen scope.
  const { judgeModelIds, costRunsPerCall, selectedConfigs } = useMemo(() => {
    const ids = new Set<string>()
    let maxRuns = 1
    const selected = enabledConfigs.filter(c => selectedMetrics.includes(c.id))
    for (const cfg of selected) {
      if (!cfg.metric?.startsWith('llm_judge_')) continue
      const params = cfg.metric_parameters || {}
      const judges = Array.isArray(params.judges) ? params.judges : null
      if (judges && judges.length > 0) {
        for (const j of judges) {
          if (j?.judge_model_id) ids.add(j.judge_model_id)
          const r = Number(j?.runs ?? 1) || 1
          if (r > maxRuns) maxRuns = r
        }
      } else if (params.judge_model) {
        ids.add(params.judge_model)
        const r = Number(params.runs_per_judge ?? 1) || 1
        if (r > maxRuns) maxRuns = r
      }
    }
    return {
      judgeModelIds: Array.from(ids),
      costRunsPerCall: maxRuns,
      selectedConfigs: selected,
    }
  }, [enabledConfigs, selectedMetrics])

  // Reset state when modal opens, then fetch the project's evaluated
  // models/annotators so the scope sections can be populated.
  useEffect(() => {
    if (!isOpen) return
    setMode('missing')
    setLoading(false)
    setSelectedMetrics(enabledConfigs.map(c => c.id))
    // C3: Clear stale lists on every open so a re-open with a different
    // projectId doesn't briefly show the previous project's models/annotators
    // before the new fetch resolves. The loading indicator below then
    // covers the gap consistently.
    setAvailableModels([])
    setAvailableAnnotators([])
    setSelectedModels([])
    setSelectedAnnotators([])

    if (!projectId) return

    let cancelled = false
    setScopeLoading(true)
    // Wrap in async IIFE so a missing client method (or any other sync
    // error in the chain) is funneled through the same fallback path as
    // a network failure — keeps test mocks that only stub runEvaluation
    // working and degrades gracefully in prod.
    ;(async () => {
      try {
        const rows = await apiClient.evaluations.getEvaluatedModels(projectId, false)
        if (cancelled) return
        const models: ScopeModel[] = []
        const annotators: ScopeAnnotator[] = []
        for (const row of rows) {
          if (row.provider === 'Annotator') {
            // Skip pre-existing annotator rows that pre-date the user_id
            // surfacing (issue #69) — without an id we can't dispatch a
            // scoped run. Backwards-compat: they just won't appear.
            if (!row.user_id) continue
            annotators.push({
              user_id: row.user_id,
              display_name: row.model_name,
            })
          } else {
            models.push({
              model_id: row.model_id,
              model_name: row.model_name,
              provider: row.provider,
            })
          }
        }
        setAvailableModels(models)
        setAvailableAnnotators(annotators)
        setSelectedModels(models.map(m => m.model_id))
        setSelectedAnnotators(annotators.map(a => a.user_id))
      } catch (err) {
        if (cancelled) return
        console.error('Failed to load evaluated models for scope picker:', err)
        setAvailableModels([])
        setAvailableAnnotators([])
        setSelectedModels([])
        setSelectedAnnotators([])
      } finally {
        if (!cancelled) setScopeLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, projectId])

  const toggleMetric = (id: string) =>
    setSelectedMetrics(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id],
    )
  const toggleModel = (id: string) =>
    setSelectedModels(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id],
    )
  const toggleAnnotator = (id: string) =>
    setSelectedAnnotators(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id],
    )

  // Run is blocked when any *rendered* scope section has zero selections.
  // The annotator section only renders when the project has annotators, so
  // a project with no annotators is unaffected by the annotator check.
  // D5: array-of-checks rather than nested ternary so each reason has a
  // single named source of truth and adding a future scope dimension is a
  // one-line append.
  const blockChecks: Array<{ blocked: boolean; reason: string }> = [
    {
      blocked: enabledConfigs.length > 0 && selectedMetrics.length === 0,
      reason: t('evaluation.controlModal.runDisabledNoMetrics', 'Mindestens eine Metrik auswählen').toString(),
    },
    {
      blocked: availableModels.length > 0 && selectedModels.length === 0,
      reason: t('evaluation.controlModal.runDisabledNoModels', 'Mindestens ein Modell auswählen').toString(),
    },
    {
      blocked: availableAnnotators.length > 0 && selectedAnnotators.length === 0,
      reason: t('evaluation.controlModal.runDisabledNoAnnotators', 'Mindestens eine:n Annotator:in auswählen').toString(),
    },
  ]
  const firstBlocker = blockChecks.find(c => c.blocked)
  const runBlocked = !!firstBlocker
  const runBlockedReason = firstBlocker?.reason ?? ''

  // Build the user-narrowed scope shared by both the callback path and the
  // built-in dispatch path. Returning `undefined` filters when the user
  // hasn't deselected anything keeps today's full-sweep semantics — only
  // explicit narrowing is sent on the wire.
  const buildScope = (): EvaluationRunScope => {
    const dispatchConfigs = enabledConfigs
      .filter(c => selectedMetrics.includes(c.id))
      .map(c => ({ ...c, enabled: true as const }))
    const modelIdsFilter =
      availableModels.length > 0 && selectedModels.length < availableModels.length
        ? selectedModels
        : undefined
    const annotatorIdsFilter =
      availableAnnotators.length > 0 &&
      selectedAnnotators.length < availableAnnotators.length
        ? selectedAnnotators
        : undefined
    return {
      evaluationConfigs: dispatchConfigs.length > 0 ? dispatchConfigs : undefined,
      modelIds: modelIdsFilter,
      annotatorUserIds: annotatorIdsFilter,
    }
  }

  const handleSubmit = async () => {
    const forceRerun = mode === 'all'

    if (onRunWithMode) {
      try {
        setLoading(true)
        await onRunWithMode(forceRerun, buildScope())
        onSuccess?.()
        onClose()
      } catch (error: any) {
        console.error('Failed to start evaluation:', error)
        addToast(
          error.message || t('evaluation.controlModal.failedToStart'),
          'error',
        )
      } finally {
        setLoading(false)
      }
      return
    }

    if (enabledConfigs.length === 0) {
      addToast(t('evaluation.controlModal.noConfigsFound'), 'error')
      return
    }
    if (!projectId) {
      addToast(t('evaluation.controlModal.projectIdRequired'), 'error')
      return
    }

    const { evaluationConfigs: dispatchConfigs = [], modelIds: modelIdsFilter, annotatorUserIds: annotatorIdsFilter } = buildScope()

    try {
      setLoading(true)
      // Each config dispatches as its own run so partial results land as
      // each metric finishes — matches the prior behavior.
      for (const config of dispatchConfigs) {
        await apiClient.evaluations.runEvaluation({
          project_id: projectId,
          evaluation_configs: [config],
          force_rerun: forceRerun,
          model_ids: modelIdsFilter,
          annotator_user_ids: annotatorIdsFilter,
        })
      }

      addToast(t('toasts.project.evaluationStarted'), 'success')
      onSuccess?.()
      onClose()
    } catch (error: any) {
      console.error('Failed to start evaluation:', error)
      addToast(
        error.response?.data?.detail || t('evaluation.controlModal.failedToStart'),
        'error',
      )
    } finally {
      setLoading(false)
    }
  }

  const costEvaluationConfigs = useMemo(
    () =>
      selectedConfigs.map(c => ({
        metric: c.metric,
        prediction_fields: c.prediction_fields,
      })),
    [selectedConfigs],
  )

  return (
    <Transition.Root show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity dark:bg-zinc-900 dark:bg-opacity-75" />
        </Transition.Child>

        <div className="fixed inset-0 z-10 overflow-y-auto">
          <div className="flex min-h-full items-end justify-center p-4 text-center sm:items-center sm:p-0">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
              enterTo="opacity-100 translate-y-0 sm:scale-100"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 translate-y-0 sm:scale-100"
              leaveTo="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
            >
              <Dialog.Panel className="relative transform overflow-hidden rounded-lg bg-white px-4 pb-4 pt-5 text-left shadow-xl transition-all dark:bg-zinc-800 sm:my-8 sm:w-full sm:max-w-4xl sm:p-6">
                <div className="absolute right-0 top-0 hidden pr-4 pt-4 sm:block">
                  <button
                    type="button"
                    className="rounded-md bg-white text-gray-400 hover:text-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 dark:bg-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-300"
                    onClick={onClose}
                  >
                    <span className="sr-only">{t('shared.alertDialog.close')}</span>
                    <XMarkIcon className="h-6 w-6" aria-hidden="true" />
                  </button>
                </div>

                <div className="sm:flex sm:items-start">
                  <div className="mt-3 w-full text-center sm:ml-4 sm:mt-0 sm:text-left">
                    <Dialog.Title
                      as="h3"
                      className="text-lg font-semibold leading-6 text-gray-900 dark:text-white"
                    >
                      {t('evaluation.controlModal.title')}
                    </Dialog.Title>

                    <div className="mt-4 space-y-4">
                      {/* Evaluation Mode */}
                      <div>
                        <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-zinc-300">
                          {t('evaluation.controlModal.evaluationMode')}
                        </label>
                        <div className="space-y-2">
                          <div className="flex items-start">
                            <input
                              id="mode-missing"
                              type="radio"
                              value="missing"
                              checked={mode === 'missing'}
                              onChange={(e) => setMode(e.target.value as 'missing')}
                              className="mr-2 mt-1"
                            />
                            <div>
                              <label htmlFor="mode-missing" className="cursor-pointer font-medium text-gray-900 dark:text-white">
                                {t('evaluation.controlModal.evaluateMissingOnly')}
                              </label>
                              <p className="text-sm text-gray-500 dark:text-zinc-400">
                                {t('evaluation.controlModal.evaluateMissingOnlyDesc')}
                              </p>
                            </div>
                          </div>
                          <div className="flex items-start">
                            <input
                              id="mode-all"
                              type="radio"
                              value="all"
                              checked={mode === 'all'}
                              onChange={(e) => setMode(e.target.value as 'all')}
                              className="mr-2 mt-1"
                            />
                            <div>
                              <label htmlFor="mode-all" className="cursor-pointer font-medium text-gray-900 dark:text-white">
                                {t('evaluation.controlModal.evaluateAll')}
                              </label>
                              <p className="text-sm text-gray-500 dark:text-zinc-400">
                                {t('evaluation.controlModal.evaluateAllDesc')}
                              </p>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Metric scope (issue #69) */}
                      {enabledConfigs.length > 0 && (
                        <div>
                          <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-zinc-300">
                            {t('evaluation.controlModal.selectMetrics', 'Metriken')}
                          </label>
                          <div className="max-h-48 space-y-2 overflow-y-auto rounded-lg border p-3 dark:border-zinc-700">
                            {enabledConfigs.map(cfg => (
                              <label key={cfg.id} htmlFor={`metric-${cfg.id}`} className="flex items-center">
                                <input
                                  id={`metric-${cfg.id}`}
                                  type="checkbox"
                                  checked={selectedMetrics.includes(cfg.id)}
                                  onChange={() => toggleMetric(cfg.id)}
                                  className="mr-2"
                                />
                                <span className="text-sm">
                                  {cfg.display_name || cfg.metric}
                                </span>
                              </label>
                            ))}
                          </div>
                          <div className="mt-2 flex justify-between text-sm">
                            <button
                              type="button"
                              onClick={() => setSelectedMetrics(enabledConfigs.map(c => c.id))}
                              className="text-blue-600 hover:text-blue-700"
                            >
                              {t('generation.controlModal.selectAll')}
                            </button>
                            <button
                              type="button"
                              onClick={() => setSelectedMetrics([])}
                              className="text-blue-600 hover:text-blue-700"
                            >
                              {t('generation.controlModal.clearAll')}
                            </button>
                          </div>
                          <div className="mt-2 text-sm text-gray-600 dark:text-zinc-400">
                            {selectedMetrics.length === 1
                              ? t('evaluation.controlModal.oneMetricSelected', '1 Metrik ausgewählt')
                              : t('evaluation.controlModal.metricsSelected', '{count} Metriken ausgewählt').toString().replace('{count}', String(selectedMetrics.length))}
                          </div>
                        </div>
                      )}

                      {/* Model scope (issue #69) */}
                      {availableModels.length > 0 && (
                        <div>
                          <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-zinc-300">
                            {t('evaluation.controlModal.selectModels', 'Modelle')}
                          </label>
                          <div className="max-h-48 space-y-2 overflow-y-auto rounded-lg border p-3 dark:border-zinc-700">
                            {availableModels.map(m => (
                              <label key={m.model_id} htmlFor={`model-${m.model_id}`} className="flex items-center">
                                <input
                                  id={`model-${m.model_id}`}
                                  type="checkbox"
                                  checked={selectedModels.includes(m.model_id)}
                                  onChange={() => toggleModel(m.model_id)}
                                  className="mr-2"
                                />
                                <span className="text-sm">{m.model_name}</span>
                              </label>
                            ))}
                          </div>
                          <div className="mt-2 flex justify-between text-sm">
                            <button
                              type="button"
                              onClick={() => setSelectedModels(availableModels.map(m => m.model_id))}
                              className="text-blue-600 hover:text-blue-700"
                            >
                              {t('generation.controlModal.selectAll')}
                            </button>
                            <button
                              type="button"
                              onClick={() => setSelectedModels([])}
                              className="text-blue-600 hover:text-blue-700"
                            >
                              {t('generation.controlModal.clearAll')}
                            </button>
                          </div>
                          <div className="mt-2 text-sm text-gray-600 dark:text-zinc-400">
                            {selectedModels.length === 1
                              ? t('generation.controlModal.oneModelSelected')
                              : t('generation.controlModal.modelsSelected', { count: selectedModels.length })}
                          </div>
                        </div>
                      )}

                      {/* Annotator scope (issue #69) */}
                      {availableAnnotators.length > 0 && (
                        <div>
                          <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-zinc-300">
                            {t('evaluation.controlModal.selectAnnotators', 'Annotator:innen')}
                          </label>
                          <div className="max-h-48 space-y-2 overflow-y-auto rounded-lg border p-3 dark:border-zinc-700">
                            {availableAnnotators.map(a => (
                              <label key={a.user_id} htmlFor={`annotator-${a.user_id}`} className="flex items-center">
                                <input
                                  id={`annotator-${a.user_id}`}
                                  type="checkbox"
                                  checked={selectedAnnotators.includes(a.user_id)}
                                  onChange={() => toggleAnnotator(a.user_id)}
                                  className="mr-2"
                                />
                                <span className="text-sm">{a.display_name}</span>
                              </label>
                            ))}
                          </div>
                          <div className="mt-2 flex justify-between text-sm">
                            <button
                              type="button"
                              onClick={() => setSelectedAnnotators(availableAnnotators.map(a => a.user_id))}
                              className="text-blue-600 hover:text-blue-700"
                            >
                              {t('generation.controlModal.selectAll')}
                            </button>
                            <button
                              type="button"
                              onClick={() => setSelectedAnnotators([])}
                              className="text-blue-600 hover:text-blue-700"
                            >
                              {t('generation.controlModal.clearAll')}
                            </button>
                          </div>
                          <div className="mt-2 text-sm text-gray-600 dark:text-zinc-400">
                            {selectedAnnotators.length === 1
                              ? t('evaluation.controlModal.oneAnnotatorSelected', '1 Annotator:in ausgewählt')
                              : t('evaluation.controlModal.annotatorsSelected', '{count} Annotator:innen ausgewählt').toString().replace('{count}', String(selectedAnnotators.length))}
                          </div>
                        </div>
                      )}

                      {/* C3: indicator visible during every scope refetch,
                          not only when both lists happen to be empty. */}
                      {scopeLoading && (
                        <div className="text-xs text-zinc-500" role="status" aria-live="polite">
                          {t('evaluation.controlModal.scopeLoading', 'Lade verfügbare Modelle und Annotator:innen…')}
                        </div>
                      )}

                      {/* C2: empty-state placeholders surface AFTER a fetch
                          settles with no rows, so the user can tell apart
                          "loading" from "project genuinely has none". */}
                      {!scopeLoading && projectId && availableModels.length === 0 && (
                        <div className="rounded-lg border border-dashed border-zinc-300 px-3 py-2 text-xs italic text-zinc-500 dark:border-zinc-700">
                          {t('evaluation.controlModal.noEvaluatedModels',
                             'Keine bewerteten Modelle in diesem Projekt')}
                        </div>
                      )}
                      {!scopeLoading && projectId && availableAnnotators.length === 0 && (
                        <div className="rounded-lg border border-dashed border-zinc-300 px-3 py-2 text-xs italic text-zinc-500 dark:border-zinc-700">
                          {t('evaluation.controlModal.noAnnotators',
                             'Keine Annotator:innen in diesem Projekt')}
                        </div>
                      )}

                      {/* Evaluation Config Summary */}
                      {displayConfigCount > 0 && (
                        <div className="rounded-lg border border-gray-300 bg-gray-50 p-3 dark:border-zinc-600 dark:bg-zinc-700">
                          <p className="text-sm font-medium text-gray-700 dark:text-zinc-300">
                            {t('evaluation.controlModal.evaluationConfigurations')}
                          </p>
                          <p className="mt-1 text-lg font-semibold text-gray-900 dark:text-white">
                            {displayConfigCount === 1
                              ? t('evaluation.controlModal.oneConfigWillBeRun')
                              : t('evaluation.controlModal.configsWillBeRun', { count: displayConfigCount })}
                          </p>
                        </div>
                      )}

                      {/* Inline cost preview — renders only when at least
                          one llm_judge_* metric is in the SELECTED set.
                          Deterministic metrics (exact_match etc.) and
                          unselected judge configs incur no API cost.
                          generationMode forwards the all/missing radio so
                          the backend counts only the judge calls that will
                          actually fire under the chosen mode. */}
                      {judgeModelIds.length > 0 && projectId && (
                        <CostEstimatePanel
                          projectId={projectId}
                          mode="evaluation"
                          judgeModels={judgeModelIds}
                          runsPerCall={costRunsPerCall}
                          enabled={isOpen}
                          modelIds={selectedModels}
                          annotatorUserIds={
                            availableAnnotators.length > 0 ? selectedAnnotators : undefined
                          }
                          evaluationConfigs={costEvaluationConfigs}
                          generationMode={mode}
                        />
                      )}
                    </div>
                  </div>
                </div>

                <div className="mt-5 flex flex-col items-end gap-2">
                  {/* C1: visible reason near the disabled CTA, announced
                      to assistive tech via role=alert + aria-describedby on
                      the button. The HTML `title` attribute alone wasn't
                      announced by screen readers. */}
                  {runBlocked && (
                    <p
                      id="run-blocked-reason"
                      role="alert"
                      className="text-xs text-amber-700 dark:text-amber-400"
                    >
                      {runBlockedReason}
                    </p>
                  )}
                  <div className="flex w-full justify-end gap-2">
                    <Button variant="outline" onClick={onClose}>
                      {t('evaluation.controlModal.cancel')}
                    </Button>
                    <Button
                      variant="filled"
                      onClick={handleSubmit}
                      disabled={
                        loading ||
                        // Block during the scope-fetch window so a fast click
                        // can't slip past unfinished selections — only matters
                        // in direct-API mode where projectId triggers the
                        // /evaluated-models call.
                        (scopeLoading && !!projectId) ||
                        runBlocked ||
                        (!onRunWithMode && enabledConfigs.length === 0)
                      }
                      aria-disabled={runBlocked || undefined}
                      aria-describedby={runBlocked ? 'run-blocked-reason' : undefined}
                      className="flex items-center gap-2"
                    >
                      <PlayIcon className="h-4 w-4" />
                      {loading
                        ? t('evaluation.controlModal.starting')
                        : t('evaluation.controlModal.startEvaluation')}
                    </Button>
                  </div>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition.Root>
  )
}
