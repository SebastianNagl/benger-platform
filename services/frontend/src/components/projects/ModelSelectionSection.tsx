/**
 * Model-selection UI block for the project detail page.
 *
 * Renders the collapsible "Model Selection" section: the available-model
 * checklist with per-model temperature / max-tokens / thinking-reasoning
 * config, plus the loading / error / read-only states.
 *
 * Extracted verbatim from ProjectDetailPage as a behavior-preserving
 * presentational sub-component — the rendered DOM/text/classNames are
 * identical to the inline version. All state, handlers and the model
 * catalog live in the parent and are prop-drilled here.
 */

'use client'

import { Button } from '@/components/shared/Button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { Tooltip } from '@/components/shared/Tooltip'
import type { Model, ModelError } from '@/hooks/useModels'
import {
  getTemperatureConstraints,
  getDefaultMaxTokens,
} from '@/lib/modelConstraints'

// Reasoning/Thinking config for models that support it
export interface ThinkingPreset {
  label: string
  value: number
}

export interface ReasoningConfig {
  parameter: string
  type: 'select' | 'budget' // 'select' for API values (low/medium/high), 'budget' for token budgets with presets
  values?: string[] // For 'select' type - API values like ['low', 'medium', 'high']
  presets?: ThinkingPreset[] // For 'budget' type - preset options with token values
  min?: number
  max?: number
  default: string | number
  label: string
}

// Provider colors for model selection badges
export const providerColors: Record<string, string> = {
  OpenAI: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200',
  Anthropic: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
  Google: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  DeepInfra: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
  Grok: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200',
  Mistral: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200',
  Cohere: 'bg-teal-100 text-teal-800 dark:bg-teal-900 dark:text-teal-200',
}

interface ModelSelectionSectionProps {
  t: (key: string, params?: any) => string
  canEditProject: () => boolean
  getReadOnlyMessage: (sectionTitle: string) => string
  expandedModels: boolean
  setExpandedModels: (value: boolean | ((prev: boolean) => boolean)) => void
  modelsLoading: boolean
  modelsError: ModelError | null
  sortedModels: Model[] | null
  availableModels: Model[]
  selectedModelIds: string[]
  modelConfigs: Record<string, any>
  handleModelToggle: (modelId: string) => void
  updateModelConfig: (modelId: string, key: string, value: any) => void
  getReasoningConfig: (modelId: string) => ReasoningConfig | undefined
  onNavigateToProfile: () => void
}

export function ModelSelectionSection({
  t,
  canEditProject,
  getReadOnlyMessage,
  expandedModels,
  setExpandedModels,
  modelsLoading,
  modelsError,
  sortedModels,
  availableModels,
  selectedModelIds,
  modelConfigs,
  handleModelToggle,
  updateModelConfig,
  getReasoningConfig,
  onNavigateToProfile,
}: ModelSelectionSectionProps) {
  return (
    <div className="bg-white dark:bg-zinc-900">
      {canEditProject() ? (
      <>
      <div className="mb-6 flex items-center justify-between">
        <button
          onClick={() => setExpandedModels(!expandedModels)}
          className="flex items-center space-x-3 text-left"
        >
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
            {t('project.modelSelection.title')}
          </h2>
          {!expandedModels && (
            <span className="rounded-md bg-zinc-100 px-2 py-1 text-sm leading-tight text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
              {modelsLoading
                ? t('project.modelSelection.loading')
                : modelsError
                  ? t('project.modelSelection.errorLoading')
                  : sortedModels
                    ? t('project.modelSelection.selectedCount', {
                        selected: selectedModelIds.length,
                        total: sortedModels.length,
                      })
                    : t('project.modelSelection.noModelsAvailable')}
            </span>
          )}
          <svg
            className={`h-5 w-5 flex-shrink-0 text-zinc-400 transition-transform ${expandedModels ? 'rotate-90 transform' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 5l7 7-7 7"
            />
          </svg>
        </button>
        {/* Per-section Save removed — card-level Speichern handles it. */}
      </div>

      {expandedModels && (
        <>
          {modelsLoading ? (
            <div className="py-6 text-center">
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                {t('project.modelSelection.loadingModels')}
              </p>
            </div>
          ) : modelsError ? (
            <div className="py-6 text-center">
              <p className="text-sm text-red-600 dark:text-red-400">
                {modelsError.type === 'NO_API_KEYS'
                  ? t('project.modelSelection.noApiKeys')
                  : modelsError.message ||
                    t('project.modelSelection.failedToLoad')}
              </p>
              {modelsError.type === 'NO_API_KEYS' && (
                <Button
                  onClick={onNavigateToProfile}
                  variant="outline"
                  className="mt-3 text-sm"
                >
                  {t('project.modelSelection.configureApiKeys')}
                </Button>
              )}
            </div>
          ) : canEditProject() ? (
            <div className="space-y-1">
              {sortedModels && sortedModels.length > 0 ? (
                <>
                  {sortedModels.map((model) => {
                    const isSelected = selectedModelIds.includes(model.id)
                    const reasoningConfig = getReasoningConfig(model.id)

                    return (
                      <div
                        key={model.id}
                        className={`rounded px-3 py-2 transition-colors ${
                          isSelected
                            ? 'bg-emerald-50 dark:bg-emerald-900/20'
                            : 'hover:bg-zinc-50 dark:hover:bg-zinc-800/50'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex min-w-0 flex-1 items-center space-x-3">
                            <input
                              id={`model-${model.id}`}
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => handleModelToggle(model.id)}
                              className="h-4 w-4 flex-shrink-0 rounded border-zinc-300 bg-white text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-700"
                            />
                            <div className="min-w-0 flex-1">
                              <label
                                htmlFor={`model-${model.id}`}
                                className="block cursor-pointer truncate text-sm font-medium text-zinc-900 dark:text-white"
                              >
                                {model.name}
                              </label>
                              {model.description && (
                                <p className="truncate text-xs text-zinc-500 dark:text-zinc-400">
                                  {model.description}
                                </p>
                              )}
                            </div>
                          </div>
                          <div className="ml-3 flex flex-shrink-0 items-center space-x-2">
                            {reasoningConfig && (
                              <span className="inline-flex items-center rounded bg-purple-100 px-1.5 py-0.5 text-xs font-medium text-purple-700 dark:bg-purple-900/30 dark:text-purple-400">
                                {t('project.modelSelection.thinking', 'Thinking')}
                              </span>
                            )}
                            <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${providerColors[model.provider] || 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200'}`}>
                              {model.provider}
                            </span>
                          </div>
                        </div>

                        {/* Model Config (Temperature, Max Tokens, Thinking/Reasoning) for selected models */}
                        {isSelected && (
                          <div className="mt-2 ml-7 flex flex-wrap items-center gap-3 border-t border-emerald-200 pt-2 dark:border-emerald-800">
                            {/* Per-model Temperature */}
                            <div className="flex items-center gap-2">
                              <label className="text-xs text-zinc-600 dark:text-zinc-400">
                                {t('project.modelSelection.temperature', 'Temp')}:
                              </label>
                              {(() => {
                                const tc = getTemperatureConstraints(availableModels?.find(m => m.id === model.id))
                                return (
                                  <Tooltip
                                    content={tc.fixed
                                      ? t('project.modelSelection.temperatureFixed', `This model requires temperature=${tc.fixedValue}`)
                                      : tc.reason
                                        ? `${tc.reason} (${tc.min}-${tc.max})`
                                        : t('project.modelSelection.temperatureTooltip', 'Response randomness (0=deterministic)')
                                    }
                                  >
                                    <input
                                      type="number"
                                      min={tc.min}
                                      max={tc.max}
                                      step={0.1}
                                      value={modelConfigs[model.id]?.temperature ?? ''}
                                      placeholder={tc.default.toString()}
                                      disabled={tc.fixed}
                                      onChange={(e) =>
                                        updateModelConfig(
                                          model.id,
                                          'temperature',
                                          e.target.value ? parseFloat(e.target.value) : undefined
                                        )
                                      }
                                      className={`h-7 w-16 rounded-md border border-zinc-300 px-2 text-xs dark:border-zinc-700 dark:bg-zinc-800 ${
                                        tc.fixed ? 'bg-zinc-100 dark:bg-zinc-900 cursor-not-allowed' : ''
                                      }`}
                                    />
                                  </Tooltip>
                                )
                              })()}
                            </div>

                            {/* Per-model Max Tokens */}
                            <div className="flex items-center gap-2">
                              <label className="text-xs text-zinc-600 dark:text-zinc-400">
                                {t('project.modelSelection.maxTokens', 'Max Tokens')}:
                              </label>
                              <input
                                type="number"
                                min={100}
                                max={128000}
                                step={100}
                                value={modelConfigs[model.id]?.max_tokens ?? ''}
                                placeholder={getDefaultMaxTokens(availableModels?.find(m => m.id === model.id))?.toString() ?? '4000'}
                                onChange={(e) =>
                                  updateModelConfig(
                                    model.id,
                                    'max_tokens',
                                    e.target.value ? parseInt(e.target.value) : undefined
                                  )
                                }
                                className="h-7 w-20 rounded-md border border-zinc-300 px-2 text-xs dark:border-zinc-700 dark:bg-zinc-800"
                              />
                            </div>

                            {/* Thinking/Reasoning Config */}
                            {reasoningConfig && (
                              <>
                                <div className="h-4 border-l border-zinc-300 dark:border-zinc-700" />
                                <label className="text-xs text-zinc-600 dark:text-zinc-400">
                                  {reasoningConfig.label}:
                                </label>
                                {reasoningConfig.type === 'select' && (
                                  <Select
                                    value={
                                      String(modelConfigs[model.id]?.[reasoningConfig.parameter] ||
                                      reasoningConfig.default)
                                    }
                                    onValueChange={(v) =>
                                      updateModelConfig(
                                        model.id,
                                        reasoningConfig.parameter,
                                        v
                                      )
                                    }
                                    displayValue={(() => {
                                      const val = String(modelConfigs[model.id]?.[reasoningConfig.parameter] || reasoningConfig.default)
                                      return val.charAt(0).toUpperCase() + val.slice(1)
                                    })()}
                                  >
                                    <SelectTrigger className="h-7 w-auto min-w-[5rem] text-xs">
                                      <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                      {reasoningConfig.values?.map((value) => (
                                        <SelectItem key={value} value={value}>
                                          {value.charAt(0).toUpperCase() + value.slice(1)}
                                        </SelectItem>
                                      ))}
                                    </SelectContent>
                                  </Select>
                                )}
                                {reasoningConfig.type === 'budget' && reasoningConfig.presets && (
                                  <>
                                    {(() => {
                                      const currentValue = modelConfigs[model.id]?.[reasoningConfig.parameter]
                                      const isCustomMode = modelConfigs[model.id]?.[`${reasoningConfig.parameter}_custom`] === true
                                      const valueMatchesPreset = reasoningConfig.presets?.some(p => p.value === currentValue)
                                      const showCustomInput = isCustomMode || (currentValue !== undefined && !valueMatchesPreset)

                                      return (
                                        <>
                                          <Select
                                            value={showCustomInput ? 'custom' : (currentValue?.toString() || reasoningConfig.default.toString())}
                                            onValueChange={(v) => {
                                              if (v === 'custom') {
                                                // Enable custom mode, keep current value or use default
                                                const val = currentValue ?? reasoningConfig.default
                                                updateModelConfig(model.id, reasoningConfig.parameter, val)
                                                updateModelConfig(model.id, `${reasoningConfig.parameter}_custom`, true)
                                              } else {
                                                // Select preset, disable custom mode
                                                updateModelConfig(model.id, reasoningConfig.parameter, parseInt(v))
                                                updateModelConfig(model.id, `${reasoningConfig.parameter}_custom`, false)
                                              }
                                            }}
                                            displayValue={(() => {
                                              if (showCustomInput) return 'Custom'
                                              const val = currentValue?.toString() || reasoningConfig.default.toString()
                                              const preset = reasoningConfig.presets?.find(p => p.value.toString() === val)
                                              return preset ? `${preset.label} (${preset.value.toLocaleString()} tokens)` : val
                                            })()}
                                          >
                                            <SelectTrigger className="h-7 w-auto min-w-[8rem] text-xs">
                                              <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                              {reasoningConfig.presets.map((preset) => (
                                                <SelectItem key={preset.value} value={preset.value.toString()}>
                                                  {preset.label} ({preset.value.toLocaleString()} tokens)
                                                </SelectItem>
                                              ))}
                                              <SelectItem value="custom">Custom</SelectItem>
                                            </SelectContent>
                                          </Select>
                                          {showCustomInput && (
                                            <input
                                              type="number"
                                              min={reasoningConfig.min}
                                              max={reasoningConfig.max}
                                              value={currentValue ?? ''}
                                              onChange={(e) =>
                                                updateModelConfig(
                                                  model.id,
                                                  reasoningConfig.parameter,
                                                  e.target.value ? parseInt(e.target.value) : undefined
                                                )
                                              }
                                              className="h-7 w-24 rounded-md border border-zinc-300 px-2 text-xs dark:border-zinc-700 dark:bg-zinc-800"
                                            />
                                          )}
                                        </>
                                      )
                                    })()}
                                    <span className="text-xs text-zinc-400">
                                      ({reasoningConfig.min?.toLocaleString()}-{reasoningConfig.max?.toLocaleString()})
                                    </span>
                                  </>
                                )}
                                {/* Show default only for select type (budget type shows range instead) */}
                                {reasoningConfig.type === 'select' && (
                                  <span className="text-xs text-zinc-400">
                                    ({t('project.modelSelection.default', 'Default')}: {String(reasoningConfig.default)})
                                  </span>
                                )}
                              </>
                            )}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </>
              ) : (
                <div className="py-6 text-center">
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    {t('project.modelSelection.noModelsForProfile')}
                  </p>
                  <Button
                    onClick={onNavigateToProfile}
                    variant="outline"
                    className="mt-3 text-sm"
                  >
                    {t('project.modelSelection.configureApiKeys')}
                  </Button>
                </div>
              )}
            </div>
          ) : (
            <div className="py-6 text-center">
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                {getReadOnlyMessage(t('project.modelSelection.title'))}
              </p>
            </div>
          )}
        </>
      )}
      </>
      ) : (
        <div className="py-6 text-center">
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            {getReadOnlyMessage(t('project.modelSelection.title'))}
          </p>
        </div>
      )}
    </div>
  )
}
