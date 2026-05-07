'use client'
import { Button } from '@/components/shared/Button'
import { CostEstimatePanel } from '@/components/shared/CostEstimateModal'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { useModels } from '@/hooks/useModels'
import { apiClient } from '@/lib/api/client'
import {
  getRecommendedParam,
  getTemperatureConstraints,
  hasRecommendations,
} from '@/lib/modelConstraints'
import { Dialog, Transition } from '@headlessui/react'
import { ExclamationTriangleIcon, XMarkIcon } from '@heroicons/react/24/outline'
import { Fragment, useEffect, useMemo, useState } from 'react'

import { Project } from '@/types/labelStudio'

interface GenerationControlModalProps {
  isOpen: boolean
  projectId?: string
  /** Available pool of model IDs to render as checkboxes. */
  models: string[]
  /** Optional set of model IDs to pre-check on open. Used by the project
   * page to carry the project's saved model selection through to the
   * trigger modal so the user doesn't have to re-tick. Defaults to `[]`
   * (no pre-selection) so unit tests of the picker UI keep their
   * empty-on-open expectation. */
  defaultSelectedModels?: string[]
  project?: Project
  onClose: () => void
  onGenerate?: (
    selectedModels: string[],
    generateMissingOnly: boolean,
    selectedStructures?: string[]
  ) => void
  onSuccess?: () => void
}

export function GenerationControlModal({
  isOpen,
  projectId,
  models,
  defaultSelectedModels = [],
  project,
  onClose,
  onGenerate,
  onSuccess,
}: GenerationControlModalProps) {
  const { addToast } = useToast()
  const { t } = useI18n()
  const [mode, setMode] = useState<'all' | 'missing'>('missing')
  const [selectedModels, setSelectedModels] = useState<string[]>([])
  const [selectedStructures, setSelectedStructures] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [temperature, setTemperature] = useState(0.0)
  const [maxTokens, setMaxTokens] = useState(4000)
  // Phase 6.6 (#6): per-run seed for variance studies. 42 keeps the
  // historical determinism behavior; researchers running multi-seed
  // studies bump this between runs. Providers/models that don't accept
  // a seed (Anthropic, Google, Kimi/MiniMax on DeepInfra) ignore it.
  const [seed, setSeed] = useState(42)
  const [modelTokenLimits, setModelTokenLimits] = useState<Record<string, number>>({})
  // Per-trigger override for runs-per-task (multi-run, migration 041). Defaults
  // to 1 in local state; the trigger sends it through only when the user
  // bumps it above 1 — a value of 1 falls back to the project default.
  const [runsPerTask, setRunsPerTask] = useState<number>(1)

  // Fetch model objects to access parameter_constraints
  const { models: availableModelObjects } = useModels()

  // Compute effective temperature constraints from selected models
  const temperatureConstraints = useMemo(() => {
    if (selectedModels.length === 0) return { min: 0, max: 2, fixed: false, fixedModels: [] as string[] }
    let effectiveMin = 0
    let effectiveMax = 2
    const fixedModels: string[] = []
    for (const modelId of selectedModels) {
      const model = availableModelObjects.find(m => m.id === modelId)
      const tc = getTemperatureConstraints(model)
      if (tc.fixed) {
        fixedModels.push(modelId)
      } else {
        effectiveMin = Math.max(effectiveMin, tc.min)
        effectiveMax = Math.min(effectiveMax, tc.max)
      }
    }
    return { min: effectiveMin, max: effectiveMax, fixed: fixedModels.length > 0, fixedModels }
  }, [selectedModels, availableModelObjects])

  // Per-key recommended-value consensus across the selected models. When
  // every selected model recommends the same value, surface it; if they
  // diverge, surface "—" + a tooltip listing the per-model values; if no
  // selected model has any recommendation, surface "Keine Empfehlung".
  // Used by the badge underneath the temperature / max_tokens inputs to
  // show the user what the providers say without forcing a click.
  const recommendedConsensus = useMemo(() => {
    function consensusFor(key: 'temperature' | 'max_tokens'): {
      value: number | undefined
      uniform: boolean
      anyRec: boolean
      perModel: Array<{ model: string; value: number | undefined }>
    } {
      if (selectedModels.length === 0) {
        return { value: undefined, uniform: false, anyRec: false, perModel: [] }
      }
      const perModel = selectedModels.map((modelId) => {
        const model = availableModelObjects.find((m) => m.id === modelId)
        const rec = getRecommendedParam(model, key, 'generation')
        return {
          model: modelId,
          value: typeof rec === 'number' ? rec : undefined,
          hasAnyRec: hasRecommendations(model),
        }
      })
      const anyRec = perModel.some((m) => m.hasAnyRec)
      const distinct = Array.from(
        new Set(perModel.map((m) => m.value).filter((v) => v !== undefined)),
      )
      const uniform = distinct.length === 1
      return {
        value: uniform ? (distinct[0] as number) : undefined,
        uniform,
        anyRec,
        perModel: perModel.map(({ model, value }) => ({ model, value })),
      }
    }
    return {
      temperature: consensusFor('temperature'),
      max_tokens: consensusFor('max_tokens'),
    }
  }, [selectedModels, availableModelObjects])

  // Get available structures from project config
  const availableStructures =
    project?.generation_config?.prompt_structures || {}
  const structureKeys = Object.keys(availableStructures)
  const hasStructures = structureKeys.length > 0

  // Reset state when modal opens. Pre-select `defaultSelectedModels`
  // (which the project page sources from
  // generation_config.selected_configuration.models) so the user's
  // project-level choice carries through to the run-trigger without
  // forcing them to re-tick everything. Defaults to `[]` for callers
  // that don't pass it (legacy behavior used by unit tests).
  //
  // Deps are intentionally `[isOpen]` only: the parent re-computes
  // `defaultSelectedModels` inline on every render so its reference is
  // unstable. If we included it in the dep array, the effect would
  // fire mid-interaction any time the parent re-rendered, blowing away
  // the user's manual deselections. We only want to reset on the
  // closed→open transition.
  useEffect(() => {
    if (isOpen) {
      setSelectedModels(defaultSelectedModels)
      setSelectedStructures([])
      setMode('missing')
      setLoading(false)
      setShowAdvanced(false)
      setTemperature(0.0)
      setMaxTokens(4000)
      setSeed(42)
      setModelTokenLimits({})
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen])

  const handleModelToggle = (modelId: string) => {
    setSelectedModels((prev) =>
      prev.includes(modelId)
        ? prev.filter((id) => id !== modelId)
        : [...prev, modelId]
    )
  }

  const handleStructureToggle = (structureKey: string) => {
    setSelectedStructures((prev) =>
      prev.includes(structureKey)
        ? prev.filter((key) => key !== structureKey)
        : [...prev, structureKey]
    )
  }

  const handleSubmit = async () => {
    if (selectedModels.length === 0) {
      addToast(t('toasts.generation.selectModel'), 'error')
      return
    }

    if (hasStructures && selectedStructures.length === 0) {
      addToast(t('toasts.generation.selectStructure'), 'error')
      return
    }

    // If onGenerate is provided (for testing), call it instead of API
    if (onGenerate) {
      onGenerate(
        selectedModels,
        mode === 'missing',
        hasStructures ? selectedStructures : undefined
      )
      onClose()
      return
    }

    try {
      setLoading(true)
      const requestBody: any = {
        mode,
        model_ids: selectedModels,
        parameters: {
          temperature,
          max_tokens: maxTokens,
          seed,
        },
      }

      // Multi-run override (migration 041). Send only when explicitly bumped
      // above 1 so the project default kicks in otherwise.
      if (runsPerTask > 1) {
        requestBody.runs_per_task = runsPerTask
      }

      // Add per-model configs if any are set
      const modelConfigs: Record<string, { max_tokens: number }> = {}
      for (const [modelId, tokens] of Object.entries(modelTokenLimits)) {
        if (tokens && tokens !== maxTokens) {
          modelConfigs[modelId] = { max_tokens: tokens }
        }
      }
      if (Object.keys(modelConfigs).length > 0) {
        requestBody.model_configs = modelConfigs
      }

      // Add structure_keys only if structures are available and selected
      if (hasStructures && selectedStructures.length > 0) {
        requestBody.structure_keys = selectedStructures
      }

      const data = await apiClient.post(
        `/generation-tasks/projects/${projectId}/generate`,
        requestBody
      )

      const { tasks_queued, models_count, estimated_time_seconds } = data

      addToast(
        t('generation.controlModal.queuedJobs', { tasks: tasks_queued, models: models_count, minutes: Math.ceil(estimated_time_seconds / 60) }),
        'success'
      )

      onSuccess?.()
    } catch (error: any) {
      console.error('Failed to start bulk generation:', error)
      addToast(
        error.response?.data?.detail || t('generation.controlModal.failedToStart'),
        'error'
      )
    } finally {
      setLoading(false)
    }
  }

  // Calculate total generations for display
  const totalGenerations =
    selectedModels.length * (hasStructures ? selectedStructures.length : 1)

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
          <div className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity" />
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
              <Dialog.Panel className="relative transform overflow-hidden rounded-lg bg-white px-4 pb-4 pt-5 text-left shadow-xl transition-all sm:my-8 sm:w-full sm:max-w-4xl sm:p-6">
                <div className="absolute right-0 top-0 hidden pr-4 pt-4 sm:block">
                  <button
                    type="button"
                    className="rounded-md bg-white text-gray-400 hover:text-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
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
                      className="text-lg font-semibold leading-6 text-gray-900"
                    >
                      {t('generation.controlModal.title')}
                    </Dialog.Title>

                    <div className="mt-4 space-y-4">
                      <h4 className="text-base font-medium text-gray-900">
                        {t('generation.controlModal.generationOptions')}
                      </h4>

                      {/* Generation Mode */}
                      <div>
                        <label className="mb-2 block text-sm font-medium text-gray-700">
                          {t('generation.controlModal.generationMode')}
                        </label>
                        <div className="space-y-2">
                          <div className="flex items-start">
                            <input
                              id="mode-missing"
                              type="radio"
                              value="missing"
                              checked={mode === 'missing'}
                              onChange={(e) =>
                                setMode(e.target.value as 'missing')
                              }
                              className="mr-2 mt-1"
                            />
                            <div>
                              <label
                                htmlFor="mode-missing"
                                className="cursor-pointer font-medium"
                              >
                                {t('generation.controlModal.generateMissingOnly')}
                              </label>
                              <p className="text-sm text-gray-500">
                                {t('generation.controlModal.generateMissingOnlyDesc')}
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
                              <label
                                htmlFor="mode-all"
                                className="cursor-pointer font-medium"
                              >
                                {t('generation.controlModal.generateAll')}
                              </label>
                              <p className="text-sm text-gray-500">
                                {t('generation.controlModal.generateAllDesc')}
                              </p>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Model Selection */}
                      <div>
                        <label className="mb-2 block text-sm font-medium text-gray-700">
                          {t('generation.controlModal.selectModels')}
                        </label>
                        <div className="max-h-48 space-y-2 overflow-y-auto rounded-lg border p-3">
                          {models.map((modelId) => (
                            <label
                              key={modelId}
                              htmlFor={`model-${modelId}`}
                              className="flex items-center"
                            >
                              <input
                                id={`model-${modelId}`}
                                type="checkbox"
                                checked={selectedModels.includes(modelId)}
                                onChange={() => handleModelToggle(modelId)}
                                className="mr-2"
                              />
                              <span className="text-sm">{modelId}</span>
                            </label>
                          ))}
                        </div>
                        <div className="mt-2 flex justify-between text-sm">
                          <button
                            type="button"
                            onClick={() => setSelectedModels(models)}
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
                        <div className="mt-2 text-sm text-gray-600">
                          {selectedModels.length === 1
                            ? t('generation.controlModal.oneModelSelected')
                            : t('generation.controlModal.modelsSelected', { count: selectedModels.length })}
                        </div>
                      </div>

                      {/* Structure Selection (Issue #762) */}
                      {hasStructures && (
                        <div>
                          <label className="mb-2 block text-sm font-medium text-gray-700">
                            {t('generation.controlModal.selectPromptStructures')}
                          </label>
                          <div className="max-h-48 space-y-2 overflow-y-auto rounded-lg border p-3">
                            {structureKeys.map((structureKey) => {
                              const structure =
                                availableStructures[structureKey]
                              return (
                                <label
                                  key={structureKey}
                                  htmlFor={`structure-${structureKey}`}
                                  className="flex items-start"
                                >
                                  <input
                                    id={`structure-${structureKey}`}
                                    type="checkbox"
                                    checked={selectedStructures.includes(
                                      structureKey
                                    )}
                                    onChange={() =>
                                      handleStructureToggle(structureKey)
                                    }
                                    className="mr-2 mt-1"
                                  />
                                  <div className="flex-1">
                                    <span className="text-sm font-medium">
                                      {structure.name}
                                    </span>
                                    {structure.description && (
                                      <p className="text-xs text-gray-500">
                                        {structure.description}
                                      </p>
                                    )}
                                  </div>
                                </label>
                              )
                            })}
                          </div>
                          <div className="mt-2 flex justify-between text-sm">
                            <button
                              type="button"
                              onClick={() =>
                                setSelectedStructures(structureKeys)
                              }
                              className="text-blue-600 hover:text-blue-700"
                            >
                              {t('generation.controlModal.selectAll')}
                            </button>
                            <button
                              type="button"
                              onClick={() => setSelectedStructures([])}
                              className="text-blue-600 hover:text-blue-700"
                            >
                              {t('generation.controlModal.clearAll')}
                            </button>
                          </div>
                          <div className="mt-2 text-sm text-gray-600">
                            {selectedStructures.length === 1
                              ? t('generation.controlModal.oneStructureSelected')
                              : t('generation.controlModal.structuresSelected', { count: selectedStructures.length })}
                          </div>
                        </div>
                      )}

                      {/* Advanced Settings (Collapsible) */}
                      <div className="border-t border-gray-200 pt-4">
                        <button
                          type="button"
                          onClick={() => setShowAdvanced(!showAdvanced)}
                          className="flex w-full items-center justify-between text-sm font-medium text-gray-700 hover:text-gray-900"
                        >
                          <span>{t('generation.controlModal.advancedSettings')}</span>
                          <span className="text-gray-400">
                            {showAdvanced ? '▼' : '▶'}
                          </span>
                        </button>

                        {showAdvanced && (
                          <div className="mt-3 space-y-4">
                            <div>
                              <label className="block text-sm font-medium text-gray-700">
                                {t('generation.controlModal.runsPerTask', 'Läufe pro Task')}
                              </label>
                              <input
                                type="number"
                                min={1}
                                max={25}
                                value={runsPerTask}
                                onChange={(e) =>
                                  setRunsPerTask(Math.max(1, Math.min(25, parseInt(e.target.value) || 1)))
                                }
                                className="mt-1 w-32 rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                              />
                              <p className="mt-1 text-xs text-gray-500">
                                {t(
                                  'generation.controlModal.runsPerTaskDesc',
                                  'Wie oft jede Task-Modell-Kombination generiert werden soll. Standardmäßig 1 — ein Wert > 1 erzeugt mehrere Trials für Varianzanalyse. Multipliziert die Kosten entsprechend.',
                                )}
                              </p>
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                              <div>
                                <label className="block text-sm font-medium text-gray-700">
                                  {t('generation.controlModal.temperature')}: {temperature.toFixed(1)}
                                </label>
                                <input
                                  type="range"
                                  min={temperatureConstraints.min}
                                  max={temperatureConstraints.max}
                                  step="0.1"
                                  value={temperature}
                                  disabled={temperatureConstraints.fixed && temperatureConstraints.fixedModels.length === selectedModels.length}
                                  onChange={(e) =>
                                    setTemperature(parseFloat(e.target.value))
                                  }
                                  className={`mt-1 w-full ${temperatureConstraints.fixed && temperatureConstraints.fixedModels.length === selectedModels.length ? 'cursor-not-allowed opacity-50' : ''}`}
                                />
                                {temperatureConstraints.fixedModels.length > 0 && (
                                  <div className="mt-1 flex items-start gap-1 text-xs text-amber-600">
                                    <ExclamationTriangleIcon className="mt-0.5 h-3 w-3 flex-shrink-0" />
                                    <span>
                                      {temperatureConstraints.fixedModels.join(', ')} {temperatureConstraints.fixedModels.length === 1 ? 'requires' : 'require'} fixed temperature=1.0. The backend will override for {temperatureConstraints.fixedModels.length === 1 ? 'this model' : 'these models'}.
                                    </span>
                                  </div>
                                )}
                                {/* Provider-recommended badge (migration 046).
                                    Shows the consensus recommendation across
                                    selected models, divergence warning when
                                    they differ, or "Keine Empfehlung" when
                                    none of the selected models carries one.
                                    A "Zurücksetzen" link sets the input back
                                    to the recommendation when the user has
                                    deviated from a uniform recommendation. */}
                                {selectedModels.length > 0 && (
                                  <div className="mt-1 text-xs">
                                    {recommendedConsensus.temperature.uniform &&
                                    recommendedConsensus.temperature.value !== undefined ? (
                                      <span className="text-zinc-600 dark:text-zinc-400">
                                        {t('generation.controlModal.recommended', 'Empfehlung')}: {recommendedConsensus.temperature.value}
                                        {temperature !== recommendedConsensus.temperature.value && (
                                          <button
                                            type="button"
                                            onClick={() =>
                                              setTemperature(
                                                recommendedConsensus.temperature.value as number,
                                              )
                                            }
                                            className="ml-2 text-blue-600 hover:underline"
                                          >
                                            {t('generation.controlModal.resetToRecommended', 'Zurücksetzen auf Empfohlen')}
                                          </button>
                                        )}
                                      </span>
                                    ) : recommendedConsensus.temperature.anyRec ? (
                                      <span
                                        className="text-amber-600 dark:text-amber-400"
                                        title={recommendedConsensus.temperature.perModel
                                          .map((m) => `${m.model}: ${m.value ?? '—'}`)
                                          .join('\n')}
                                      >
                                        {t('generation.controlModal.divergentRecommendations', 'Verschiedene Empfehlungen pro Modell')}
                                      </span>
                                    ) : (
                                      <span className="text-zinc-400 dark:text-zinc-500">
                                        {t('generation.controlModal.noRecommendation', 'Keine Empfehlung')}
                                      </span>
                                    )}
                                  </div>
                                )}
                                <p className="mt-1 text-xs text-gray-500">
                                  {t('generation.controlModal.temperatureDesc')}
                                </p>
                              </div>
                              <div>
                                <label className="block text-sm font-medium text-gray-700">
                                  {t('generation.controlModal.defaultMaxTokens')}
                                </label>
                                <input
                                  type="number"
                                  min="100"
                                  max="16000"
                                  value={maxTokens}
                                  onChange={(e) =>
                                    setMaxTokens(parseInt(e.target.value) || 4000)
                                  }
                                  className="mt-1 w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                                />
                                {/* Same recommended-badge pattern for max_tokens. */}
                                {selectedModels.length > 0 && (
                                  <div className="mt-1 text-xs">
                                    {recommendedConsensus.max_tokens.uniform &&
                                    recommendedConsensus.max_tokens.value !== undefined ? (
                                      <span className="text-zinc-600 dark:text-zinc-400">
                                        {t('generation.controlModal.recommended', 'Empfehlung')}: {recommendedConsensus.max_tokens.value}
                                        {maxTokens !== recommendedConsensus.max_tokens.value && (
                                          <button
                                            type="button"
                                            onClick={() =>
                                              setMaxTokens(
                                                recommendedConsensus.max_tokens.value as number,
                                              )
                                            }
                                            className="ml-2 text-blue-600 hover:underline"
                                          >
                                            {t('generation.controlModal.resetToRecommended', 'Zurücksetzen auf Empfohlen')}
                                          </button>
                                        )}
                                      </span>
                                    ) : recommendedConsensus.max_tokens.anyRec ? (
                                      <span
                                        className="text-amber-600 dark:text-amber-400"
                                        title={recommendedConsensus.max_tokens.perModel
                                          .map((m) => `${m.model}: ${m.value ?? '—'}`)
                                          .join('\n')}
                                      >
                                        {t('generation.controlModal.divergentRecommendations', 'Verschiedene Empfehlungen pro Modell')}
                                      </span>
                                    ) : (
                                      <span className="text-zinc-400 dark:text-zinc-500">
                                        {t('generation.controlModal.noRecommendation', 'Keine Empfehlung')}
                                      </span>
                                    )}
                                  </div>
                                )}
                                <p className="mt-1 text-xs text-gray-500">
                                  {t('generation.controlModal.defaultMaxTokensDesc')}
                                </p>
                              </div>
                            </div>
                            {/* Phase 6.6 (#6): per-run seed input */}
                            <div>
                              <label className="block text-sm font-medium text-gray-700">
                                {t('generation.controlModal.seed')}
                              </label>
                              <input
                                type="number"
                                min={0}
                                value={seed}
                                onChange={(e) =>
                                  setSeed(parseInt(e.target.value) || 42)
                                }
                                className="mt-1 w-32 rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                              />
                              <p className="mt-1 text-xs text-gray-500">
                                {t('generation.controlModal.seedDesc')}
                              </p>
                            </div>

                            {/* Per-Model Token Limits */}
                            {selectedModels.length > 0 && (
                              <div>
                                <label className="block text-sm font-medium text-gray-700">
                                  {t('generation.controlModal.perModelTokenLimits')}
                                </label>
                                <p className="mb-2 text-xs text-gray-500">
                                  {t('generation.controlModal.perModelTokenLimitsDesc')}
                                </p>
                                <div className="max-h-32 space-y-2 overflow-y-auto rounded-lg border border-gray-200 bg-gray-50 p-2">
                                  {selectedModels.map((modelId) => (
                                    <div key={modelId} className="flex items-center gap-2">
                                      <span className="min-w-0 flex-1 truncate text-sm text-gray-700">
                                        {modelId}
                                      </span>
                                      <input
                                        type="number"
                                        min="100"
                                        max="16000"
                                        placeholder={maxTokens.toString()}
                                        value={modelTokenLimits[modelId] || ''}
                                        onChange={(e) => {
                                          const value = e.target.value
                                          setModelTokenLimits((prev) => {
                                            if (value === '') {
                                              const { [modelId]: _, ...rest } = prev
                                              return rest
                                            }
                                            return {
                                              ...prev,
                                              [modelId]: parseInt(value) || 0,
                                            }
                                          })
                                        }}
                                        className="w-24 rounded-md border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                                      />
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </div>

                      {/* Generation Count Info */}
                      {selectedModels.length > 0 &&
                        (hasStructures
                          ? selectedStructures.length > 0
                          : true) && (
                          <div className="rounded-lg border border-gray-300 bg-gray-50 p-3">
                            <p className="text-sm font-medium text-gray-700">
                              {t('generation.controlModal.totalGenerationsPerTask')}
                            </p>
                            <p className="mt-1 text-lg font-semibold text-gray-900">
                              {selectedModels.length} {selectedModels.length !== 1 ? t('generation.controlModal.models') : t('generation.controlModal.model')}
                              {hasStructures && (
                                <>
                                  {' '}
                                  × {selectedStructures.length} {selectedStructures.length !== 1 ? t('generation.controlModal.structures') : t('generation.controlModal.structure')}
                                </>
                              )}
                              {' = '}
                              {totalGenerations} {totalGenerations !== 1 ? t('generation.controlModal.generations') : t('generation.controlModal.generation')}
                            </p>
                          </div>
                        )}

                    </div>
                  </div>
                </div>

                {selectedModels.length > 0 && projectId && (
                  <div className="mt-5">
                    <CostEstimatePanel
                      projectId={projectId}
                      mode="generation"
                      modelIds={selectedModels}
                      runsPerCall={runsPerTask}
                      enabled={isOpen}
                    />
                  </div>
                )}
                <div className="mt-5 sm:mt-4 sm:flex sm:flex-row-reverse sm:gap-2">
                  <Button
                    variant="filled"
                    onClick={handleSubmit}
                    disabled={
                      loading ||
                      selectedModels.length === 0 ||
                      (hasStructures && selectedStructures.length === 0)
                    }
                  >
                    {loading ? t('generation.controlModal.starting') : t('generation.controlModal.startGeneration')}
                  </Button>
                  <Button variant="outline" onClick={onClose}>
                    {t('generation.controlModal.cancel')}
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
