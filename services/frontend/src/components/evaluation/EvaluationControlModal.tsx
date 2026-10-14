'use client'

import { Alert } from '@/components/shared/Alert'
import { BillingOrgSelect } from '@/components/shared/BillingOrgSelect'
import { Button } from '@/components/shared/Button'
import { CostEstimatePanel } from '@/components/shared/CostEstimatePanel'
import {
  RUN_DIALOG as R,
  SelectionFooter,
} from '@/components/shared/RunDialogParts'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { useBillingOrganization } from '@/hooks/useBillingOrganization'
import { apiClient } from '@/lib/api/client'
import { metricDisplayLabel } from '@/lib/evaluation/runDisplay'
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
  /** Same semantics as `modelIds` but for generation prompt structures:
   *  undefined = no filter (all structures), otherwise the run only grades
   *  generations produced under the named structure keys. */
  structureKeys?: string[]
  /** The org whose keys pay for the judge calls ("billed to"); undefined =
   *  the server's default rule. */
  billingOrganizationId?: string
}

/** A config's name in the metric picker: its own name, else the metric's
 *  readable name, with the judge model when several configs share a name. */
function configOptionLabel(
  cfg: EvaluationConfigInput,
  all: ReadonlyArray<EvaluationConfigInput>,
  t: (key: string, vars?: Record<string, unknown>) => string,
): string {
  const base = (c: EvaluationConfigInput) =>
    c.display_name || metricDisplayLabel(c.metric, undefined, t)
  const label = base(cfg)
  const judge = cfg.metric_parameters?.judge_model
  const shared = all.filter((c) => base(c) === label).length > 1
  return shared && typeof judge === 'string' && judge
    ? `${label} · ${judge}`
    : label
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
  onRunWithMode?: (
    forceRerun: boolean,
    scope?: EvaluationRunScope,
  ) => Promise<void>
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

interface ScopeStructure {
  key: string
  name: string
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
  const { billingOrganizationId } = useBillingOrganization(projectId)
  const [mode, setMode] = useState<'all' | 'missing'>('missing')
  const [loading, setLoading] = useState(false)

  // Scope state (issue #69). Each list is the user's CURRENT selection;
  // the available* lists are populated from /evaluated-models on open.
  // Defaults to all-selected so today's full-sweep behavior is preserved
  // when the user just hits Run without touching anything.
  const [availableModels, setAvailableModels] = useState<ScopeModel[]>([])
  const [availableAnnotators, setAvailableAnnotators] = useState<
    ScopeAnnotator[]
  >([])
  const [availableStructures, setAvailableStructures] = useState<
    ScopeStructure[]
  >([])
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>([])
  const [selectedModels, setSelectedModels] = useState<string[]>([])
  const [selectedAnnotators, setSelectedAnnotators] = useState<string[]>([])
  const [selectedStructures, setSelectedStructures] = useState<string[]>([])
  const [scopeLoading, setScopeLoading] = useState(false)

  const allConfigs = evaluationConfigs ?? []
  const enabledConfigs = useMemo(
    () => allConfigs.filter((c) => c.enabled !== false),
    [allConfigs],
  )
  const displayConfigCount = configCount ?? enabledConfigs.length

  // Derive judge models + max runs across SELECTED llm_judge_* metrics for
  // the inline cost-preview panel. Recomputes when the metric selection
  // changes so the dollar number tracks the chosen scope.
  const { judgeModelIds, costRunsPerCall, selectedConfigs } = useMemo(() => {
    const ids = new Set<string>()
    let maxRuns = 1
    const selected = enabledConfigs.filter((c) =>
      selectedMetrics.includes(c.id),
    )
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
    setSelectedMetrics(enabledConfigs.map((c) => c.id))
    // C3: Clear stale lists on every open so a re-open with a different
    // projectId doesn't briefly show the previous project's models/annotators
    // before the new fetch resolves. The loading indicator below then
    // covers the gap consistently.
    setAvailableModels([])
    setAvailableAnnotators([])
    setAvailableStructures([])
    setSelectedModels([])
    setSelectedAnnotators([])
    setSelectedStructures([])

    if (!projectId) return

    let cancelled = false
    setScopeLoading(true)
    // Wrap in async IIFE so a missing client method (or any other sync
    // error in the chain) is funneled through the same fallback path as
    // a network failure — keeps test mocks that only stub runEvaluation
    // working and degrades gracefully in prod.
    ;(async () => {
      try {
        const rows = await apiClient.evaluations.getEvaluatedModels(
          projectId,
          false,
        )
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
        setSelectedModels(models.map((m) => m.model_id))
        setSelectedAnnotators(annotators.map((a) => a.user_id))
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
      // Prompt-structure scope: fetched separately so a failure here (e.g.
      // no generation config on the project) degrades to "no structure
      // section" without touching the model/annotator pickers above.
      try {
        const structuresData: Record<string, { name?: string }> | null =
          await apiClient.get(
            `/projects/${projectId}/generation-config/structures`,
          )
        if (cancelled) return
        const structures: ScopeStructure[] = Object.entries(
          structuresData || {},
        ).map(([key, s]) => ({ key, name: s?.name || key }))
        setAvailableStructures(structures)
        setSelectedStructures(structures.map((s) => s.key))
      } catch {
        if (cancelled) return
        setAvailableStructures([])
        setSelectedStructures([])
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, projectId])

  const toggleMetric = (id: string) =>
    setSelectedMetrics((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  const toggleModel = (id: string) =>
    setSelectedModels((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  const toggleAnnotator = (id: string) =>
    setSelectedAnnotators((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  const toggleStructure = (key: string) =>
    setSelectedStructures((prev) =>
      prev.includes(key) ? prev.filter((x) => x !== key) : [...prev, key],
    )

  // The structure section only renders when scoping is meaningful: with a
  // single (or no) prompt structure every generation belongs to it anyway.
  const showStructureScope = availableStructures.length > 1

  // Run is blocked when any *rendered* scope section has zero selections.
  // The annotator section only renders when the project has annotators, so
  // a project with no annotators is unaffected by the annotator check.
  // D5: array-of-checks rather than nested ternary so each reason has a
  // single named source of truth and adding a future scope dimension is a
  // one-line append.
  const blockChecks: Array<{ blocked: boolean; reason: string }> = [
    {
      blocked: enabledConfigs.length > 0 && selectedMetrics.length === 0,
      reason: t('evaluation.controlModal.runDisabledNoMetrics').toString(),
    },
    {
      // No model deselects the generation side and no annotator the answer
      // side ("model generations only"); leaving both empty grades nothing.
      blocked:
        (availableModels.length > 0 || availableAnnotators.length > 0) &&
        selectedModels.length === 0 &&
        selectedAnnotators.length === 0,
      reason: (availableAnnotators.length === 0
        ? t('evaluation.controlModal.runDisabledNoModels')
        : availableModels.length === 0
          ? t('evaluation.controlModal.runDisabledNoAnnotators')
          : t('evaluation.controlModal.runDisabledNoSubjects')
      ).toString(),
    },
    {
      blocked: showStructureScope && selectedStructures.length === 0,
      reason: t('evaluation.controlModal.runDisabledNoStructures').toString(),
    },
  ]
  const firstBlocker = blockChecks.find((c) => c.blocked)
  const runBlocked = !!firstBlocker
  const runBlockedReason = firstBlocker?.reason ?? ''

  // Build the user-narrowed scope shared by both the callback path and the
  // built-in dispatch path. Returning `undefined` filters when the user
  // hasn't deselected anything keeps today's full-sweep semantics — only
  // explicit narrowing is sent on the wire.
  const buildScope = (): EvaluationRunScope => {
    const dispatchConfigs = enabledConfigs
      .filter((c) => selectedMetrics.includes(c.id))
      .map((c) => ({ ...c, enabled: true as const }))
    const modelIdsFilter =
      availableModels.length > 0 &&
      selectedModels.length < availableModels.length
        ? selectedModels
        : undefined
    const annotatorIdsFilter =
      availableAnnotators.length > 0 &&
      selectedAnnotators.length < availableAnnotators.length
        ? selectedAnnotators
        : undefined
    const structureKeysFilter =
      showStructureScope &&
      selectedStructures.length < availableStructures.length
        ? selectedStructures
        : undefined
    return {
      evaluationConfigs:
        dispatchConfigs.length > 0 ? dispatchConfigs : undefined,
      modelIds: modelIdsFilter,
      annotatorUserIds: annotatorIdsFilter,
      structureKeys: structureKeysFilter,
      billingOrganizationId: billingOrganizationId ?? undefined,
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

    const {
      evaluationConfigs: dispatchConfigs = [],
      modelIds: modelIdsFilter,
      annotatorUserIds: annotatorIdsFilter,
      structureKeys: structureKeysFilter,
      billingOrganizationId: billingOrgId,
    } = buildScope()

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
          structure_keys: structureKeysFilter,
          billing_organization_id: billingOrgId,
        })
      }

      addToast(t('toasts.project.evaluationStarted'), 'success')
      onSuccess?.()
      onClose()
    } catch (error: any) {
      console.error('Failed to start evaluation:', error)
      addToast(
        error.response?.data?.detail ||
          t('evaluation.controlModal.failedToStart'),
        'error',
      )
    } finally {
      setLoading(false)
    }
  }

  const costEvaluationConfigs = useMemo(
    () =>
      selectedConfigs.map((c) => ({
        id: c.id,
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
          <div className={R.overlay} />
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
              <Dialog.Panel className={R.panel}>
                <div className="absolute top-0 right-0 hidden pt-4 pr-4 sm:block">
                  <button
                    type="button"
                    className={R.closeButton}
                    onClick={onClose}
                  >
                    <span className="sr-only">
                      {t('shared.alertDialog.close')}
                    </span>
                    <XMarkIcon className="h-6 w-6" aria-hidden="true" />
                  </button>
                </div>

                <Dialog.Title as="h3" className={R.title}>
                  {t('evaluation.controlModal.title')}
                </Dialog.Title>

                <div className="mt-5 space-y-6">
                  <BillingOrgSelect projectId={projectId} />

                  {/* Evaluation Mode */}
                  <div>
                    <label className={R.sectionLabel}>
                      {t('evaluation.controlModal.evaluationMode')}
                    </label>
                    <div className="space-y-2">
                      <div className={R.optionCard}>
                        <input
                          id="mode-missing"
                          type="radio"
                          value="missing"
                          checked={mode === 'missing'}
                          onChange={(e) => setMode(e.target.value as 'missing')}
                          className={R.radio}
                        />
                        <div className="flex-1">
                          <label
                            htmlFor="mode-missing"
                            className={R.optionTitle}
                          >
                            {t('evaluation.controlModal.evaluateMissingOnly')}
                          </label>
                          <p className={R.optionDescription}>
                            {t(
                              'evaluation.controlModal.evaluateMissingOnlyDesc',
                            )}
                          </p>
                        </div>
                      </div>
                      <div className={R.optionCard}>
                        <input
                          id="mode-all"
                          type="radio"
                          value="all"
                          checked={mode === 'all'}
                          onChange={(e) => setMode(e.target.value as 'all')}
                          className={R.radio}
                        />
                        <div className="flex-1">
                          <label htmlFor="mode-all" className={R.optionTitle}>
                            {t('evaluation.controlModal.evaluateAll')}
                          </label>
                          <p className={R.optionDescription}>
                            {t('evaluation.controlModal.evaluateAllDesc')}
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Metric scope (issue #69) */}
                  {enabledConfigs.length > 0 && (
                    <div>
                      <label className={R.sectionLabel}>
                        {t('evaluation.controlModal.selectMetrics')}
                      </label>
                      <div className={R.checkList}>
                        {enabledConfigs.map((cfg) => (
                          <label
                            key={cfg.id}
                            htmlFor={`metric-${cfg.id}`}
                            className={R.checkRow}
                          >
                            <input
                              id={`metric-${cfg.id}`}
                              type="checkbox"
                              checked={selectedMetrics.includes(cfg.id)}
                              onChange={() => toggleMetric(cfg.id)}
                              className={R.checkbox}
                            />
                            <span>
                              {configOptionLabel(cfg, enabledConfigs, t)}
                            </span>
                          </label>
                        ))}
                      </div>
                      <SelectionFooter
                        summary={
                          selectedMetrics.length === 1
                            ? t('evaluation.controlModal.oneMetricSelected')
                            : t('evaluation.controlModal.metricsSelected')
                                .toString()
                                .replace(
                                  '{count}',
                                  String(selectedMetrics.length),
                                )
                        }
                        selectAllLabel={t('generation.controlModal.selectAll')}
                        clearAllLabel={t('generation.controlModal.clearAll')}
                        onSelectAll={() =>
                          setSelectedMetrics(enabledConfigs.map((c) => c.id))
                        }
                        onClearAll={() => setSelectedMetrics([])}
                      />
                    </div>
                  )}

                  {/* Model scope (issue #69) */}
                  {availableModels.length > 0 && (
                    <div>
                      <label className={R.sectionLabel}>
                        {t('evaluation.controlModal.selectModels')}
                      </label>
                      <div className={R.checkList}>
                        {availableModels.map((m) => (
                          <label
                            key={m.model_id}
                            htmlFor={`model-${m.model_id}`}
                            className={R.checkRow}
                          >
                            <input
                              id={`model-${m.model_id}`}
                              type="checkbox"
                              checked={selectedModels.includes(m.model_id)}
                              onChange={() => toggleModel(m.model_id)}
                              className={R.checkbox}
                            />
                            <span>{m.model_name}</span>
                          </label>
                        ))}
                      </div>
                      <SelectionFooter
                        summary={
                          selectedModels.length === 1
                            ? t('generation.controlModal.oneModelSelected')
                            : t('generation.controlModal.modelsSelected', {
                                count: selectedModels.length,
                              })
                        }
                        selectAllLabel={t('generation.controlModal.selectAll')}
                        clearAllLabel={t('generation.controlModal.clearAll')}
                        onSelectAll={() =>
                          setSelectedModels(
                            availableModels.map((m) => m.model_id),
                          )
                        }
                        onClearAll={() => setSelectedModels([])}
                      />
                      {selectedModels.length === 0 &&
                        selectedAnnotators.length > 0 && (
                          <p className={`mt-1 ${R.hint}`}>
                            {t('evaluation.controlModal.answersOnlyHint')}
                          </p>
                        )}
                    </div>
                  )}

                  {/* Annotator scope (issue #69) */}
                  {availableAnnotators.length > 0 && (
                    <div>
                      <label className={R.sectionLabel}>
                        {t('evaluation.controlModal.selectAnnotators')}
                      </label>
                      <div className={R.checkList}>
                        {availableAnnotators.map((a) => (
                          <label
                            key={a.user_id}
                            htmlFor={`annotator-${a.user_id}`}
                            className={R.checkRow}
                          >
                            <input
                              id={`annotator-${a.user_id}`}
                              type="checkbox"
                              checked={selectedAnnotators.includes(a.user_id)}
                              onChange={() => toggleAnnotator(a.user_id)}
                              className={R.checkbox}
                            />
                            <span>{a.display_name}</span>
                          </label>
                        ))}
                      </div>
                      <SelectionFooter
                        summary={
                          selectedAnnotators.length === 1
                            ? t('evaluation.controlModal.oneAnnotatorSelected')
                            : t('evaluation.controlModal.annotatorsSelected')
                                .toString()
                                .replace(
                                  '{count}',
                                  String(selectedAnnotators.length),
                                )
                        }
                        selectAllLabel={t('generation.controlModal.selectAll')}
                        clearAllLabel={t('generation.controlModal.clearAll')}
                        onSelectAll={() =>
                          setSelectedAnnotators(
                            availableAnnotators.map((a) => a.user_id),
                          )
                        }
                        onClearAll={() => setSelectedAnnotators([])}
                      />
                      {selectedAnnotators.length === 0 &&
                        selectedModels.length > 0 && (
                          <p className={`mt-1 ${R.hint}`}>
                            {t('evaluation.controlModal.modelsOnlyHint')}
                          </p>
                        )}
                    </div>
                  )}

                  {/* Prompt-structure scope: narrows the run to
                      generations produced under specific prompt
                      structures. Only rendered when the project defines
                      more than one structure — with a single structure
                      the filter is a no-op. */}
                  {showStructureScope && (
                    <div>
                      <label className={R.sectionLabel}>
                        {t('evaluation.controlModal.selectStructures')}
                      </label>
                      <div className={R.checkList}>
                        {availableStructures.map((s) => (
                          <label
                            key={s.key}
                            htmlFor={`structure-${s.key}`}
                            className={R.checkRow}
                          >
                            <input
                              id={`structure-${s.key}`}
                              type="checkbox"
                              checked={selectedStructures.includes(s.key)}
                              onChange={() => toggleStructure(s.key)}
                              className={R.checkbox}
                            />
                            <span>
                              {s.name}
                              {s.name !== s.key && (
                                <span className="ml-1 text-xs text-zinc-400 dark:text-zinc-500">
                                  ({s.key})
                                </span>
                              )}
                            </span>
                          </label>
                        ))}
                      </div>
                      <SelectionFooter
                        summary={
                          selectedStructures.length === 1
                            ? t('evaluation.controlModal.oneStructureSelected')
                            : t('evaluation.controlModal.structuresSelected')
                                .toString()
                                .replace(
                                  '{count}',
                                  String(selectedStructures.length),
                                )
                        }
                        selectAllLabel={t('generation.controlModal.selectAll')}
                        clearAllLabel={t('generation.controlModal.clearAll')}
                        onSelectAll={() =>
                          setSelectedStructures(
                            availableStructures.map((s) => s.key),
                          )
                        }
                        onClearAll={() => setSelectedStructures([])}
                      />
                    </div>
                  )}

                  {/* C3: indicator visible during every scope refetch,
                      not only when both lists happen to be empty. */}
                  {scopeLoading && (
                    <div className={R.hint} role="status" aria-live="polite">
                      {t('evaluation.controlModal.scopeLoading')}
                    </div>
                  )}

                  {/* C2: empty-state placeholders surface AFTER a fetch
                      settles with no rows, so the user can tell apart
                      "loading" from "project genuinely has none". */}
                  {!scopeLoading &&
                    projectId &&
                    availableModels.length === 0 && (
                      <div className={R.emptyState}>
                        {t('evaluation.controlModal.noEvaluatedModels')}
                      </div>
                    )}
                  {!scopeLoading &&
                    projectId &&
                    availableAnnotators.length === 0 && (
                      <div className={R.emptyState}>
                        {t('evaluation.controlModal.noAnnotators')}
                      </div>
                    )}

                  {/* Evaluation Config Summary */}
                  {displayConfigCount > 0 && (
                    <div className={R.summaryBox}>
                      <p className={R.summaryLabel}>
                        {t('evaluation.controlModal.evaluationConfigurations')}
                      </p>
                      <p className={R.summaryValue}>
                        {displayConfigCount === 1
                          ? t('evaluation.controlModal.oneConfigWillBeRun')
                          : t('evaluation.controlModal.configsWillBeRun', {
                              count: displayConfigCount,
                            })}
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
                      modelIds={
                        availableModels.length > 0 ? selectedModels : undefined
                      }
                      annotatorUserIds={
                        availableAnnotators.length > 0
                          ? selectedAnnotators
                          : undefined
                      }
                      evaluationConfigs={costEvaluationConfigs}
                      generationMode={mode}
                      structureKeys={
                        showStructureScope ? selectedStructures : undefined
                      }
                    />
                  )}

                  {/* C1: visible reason near the disabled CTA, announced
                      to assistive tech via role=alert + aria-describedby on
                      the button. The HTML `title` attribute alone wasn't
                      announced by screen readers. */}
                  {runBlocked && (
                    <Alert variant="warning" className="p-3">
                      <p
                        id="run-blocked-reason"
                        role="alert"
                        className="text-sm text-amber-800 dark:text-amber-300"
                      >
                        {runBlockedReason}
                      </p>
                    </Alert>
                  )}
                </div>

                <div className="mt-6 flex justify-end gap-2">
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
                    aria-describedby={
                      runBlocked ? 'run-blocked-reason' : undefined
                    }
                  >
                    <PlayIcon className="h-4 w-4" aria-hidden="true" />
                    {loading
                      ? t('evaluation.controlModal.starting')
                      : t('evaluation.controlModal.startEvaluation')}
                  </Button>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition.Root>
  )
}
