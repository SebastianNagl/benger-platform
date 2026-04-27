'use client'

import { Card } from '@/components/shared/Card'
import { Input } from '@/components/shared/Input'
import { Label } from '@/components/shared/Label'
import { useI18n } from '@/contexts/I18nContext'
import { useModels } from '@/hooks/useModels'
import { cn } from '@/lib/utils'
import {
  AdjustmentsHorizontalIcon,
  ChevronDownIcon,
  ChevronUpIcon,
} from '@heroicons/react/24/outline'
import { useState } from 'react'
import { GenerationParameters, ModelConfig } from './types'

interface StepModelsProps {
  selectedModelIds: string[]
  modelConfigs: Record<string, ModelConfig>
  generationParameters: GenerationParameters
  onSelectedModelsChange: (ids: string[]) => void
  onModelConfigsChange: (configs: Record<string, ModelConfig>) => void
  onGenerationParametersChange: (params: GenerationParameters) => void
}

const PROVIDER_COLORS: Record<string, string> = {
  openai: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  anthropic: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
  google: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  deepinfra: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300',
  mistral: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-300',
  cohere: 'bg-pink-100 text-pink-800 dark:bg-pink-900/30 dark:text-pink-300',
  grok: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
}

export function StepModels({
  selectedModelIds,
  modelConfigs,
  onSelectedModelsChange,
  onModelConfigsChange,
  generationParameters,
  onGenerationParametersChange,
}: StepModelsProps) {
  const { t } = useI18n()
  const { models, loading, error } = useModels()
  const [expandedModel, setExpandedModel] = useState<string | null>(null)
  const [showDefaults, setShowDefaults] = useState(false)

  // Group models by provider
  const groupedModels = models.reduce(
    (acc, model) => {
      const provider = model.provider || 'other'
      if (!acc[provider]) acc[provider] = []
      acc[provider].push(model)
      return acc
    },
    {} as Record<string, typeof models>
  )

  const toggleModel = (modelId: string) => {
    if (selectedModelIds.includes(modelId)) {
      onSelectedModelsChange(selectedModelIds.filter((id) => id !== modelId))
      const newConfigs = { ...modelConfigs }
      delete newConfigs[modelId]
      onModelConfigsChange(newConfigs)
    } else {
      onSelectedModelsChange([...selectedModelIds, modelId])
    }
  }

  const updateConfig = (
    modelId: string,
    field: keyof ModelConfig,
    value: number | undefined
  ) => {
    onModelConfigsChange({
      ...modelConfigs,
      [modelId]: { ...modelConfigs[modelId], [field]: value },
    })
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="mb-2 text-2xl font-semibold text-zinc-900 dark:text-white">
          {t('projects.creation.wizard.step5.title')}
        </h2>
        <p className="text-zinc-600 dark:text-zinc-400">
          {t('projects.creation.wizard.step5.subtitle')}
        </p>
      </div>

      {loading && (
        <div className="py-8 text-center text-zinc-500">
          {t('projects.creation.wizard.step5.loading')}
        </div>
      )}

      {error && error.type === 'NO_API_KEYS' && (
        <Card>
          <div className="p-6 text-center">
            <p className="mb-2 text-zinc-600 dark:text-zinc-400">
              {t('projects.creation.wizard.step5.noApiKeys')}
            </p>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              {t('projects.creation.wizard.step5.noApiKeysHint')}
            </p>
          </div>
        </Card>
      )}

      {!loading && models.length > 0 && (
        <div className="space-y-4">
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            {t('projects.creation.wizard.step5.selectedCount', {
              count: selectedModelIds.length,
              total: models.length,
            })}
          </p>

          {Object.entries(groupedModels).map(([provider, providerModels]) => (
            <div key={provider}>
              <div className="mb-2 flex items-center gap-2">
                <span
                  className={cn(
                    'rounded-md px-2 py-0.5 text-xs font-medium capitalize',
                    PROVIDER_COLORS[provider] ||
                      'bg-zinc-100 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-300'
                  )}
                >
                  {provider}
                </span>
              </div>

              <div className="space-y-2">
                {providerModels.map((model) => {
                  const isSelected = selectedModelIds.includes(model.id)
                  const isExpanded = expandedModel === model.id

                  const config = modelConfigs[model.id] || {}

                  return (
                    <div key={model.id}>
                      <div className="flex items-center justify-between">
                        <div className="flex-1">
                          <p className="text-sm font-medium text-zinc-900 dark:text-white">
                            {model.name}
                          </p>
                          {model.description && (
                            <p className="text-xs text-zinc-500 dark:text-zinc-400">
                              {model.description}
                            </p>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          {isSelected && (
                            <button
                              type="button"
                              onClick={() =>
                                setExpandedModel(
                                  isExpanded ? null : model.id
                                )
                              }
                              className="text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300"
                            >
                              {isExpanded ? (
                                <ChevronUpIcon className="h-4 w-4" />
                              ) : (
                                <ChevronDownIcon className="h-4 w-4" />
                              )}
                            </button>
                          )}
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleModel(model.id)}
                            className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                            data-testid={`wizard-model-${model.id}`}
                          />
                        </div>
                      </div>

                      {isSelected && isExpanded && (
                        <div className="ml-4 mt-2 rounded-lg border border-zinc-200 p-3 dark:border-zinc-700">
                          <div className="grid grid-cols-2 gap-3">
                            <div>
                              <Label className="text-xs">
                                {t(
                                  'projects.creation.wizard.step5.temperature'
                                )}
                              </Label>
                              <Input
                                type="number"
                                min={0}
                                max={
                                  model.parameter_constraints?.temperature
                                    ?.max ?? 2
                                }
                                step={0.1}
                                value={config.temperature ?? ''}
                                onChange={(e) =>
                                  updateConfig(
                                    model.id,
                                    'temperature',
                                    e.target.value
                                      ? Number(e.target.value)
                                      : undefined
                                  )
                                }
                                placeholder={String(
                                  model.parameter_constraints?.temperature
                                    ?.default ?? 0.7
                                )}
                                className="text-sm"
                              />
                            </div>
                            <div>
                              <Label className="text-xs">
                                {t(
                                  'projects.creation.wizard.step5.maxTokens'
                                )}
                              </Label>
                              <Input
                                type="number"
                                min={1}
                                value={config.max_tokens ?? ''}
                                onChange={(e) =>
                                  updateConfig(
                                    model.id,
                                    'max_tokens',
                                    e.target.value
                                      ? Number(e.target.value)
                                      : undefined
                                  )
                                }
                                placeholder={String(
                                  model.parameter_constraints?.max_tokens
                                    ?.default ?? 4096
                                )}
                                className="text-sm"
                              />
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Default generation parameters (collapsible) */}
      <div className="rounded-lg border border-zinc-200 dark:border-zinc-700">
        <button
          type="button"
          onClick={() => setShowDefaults(!showDefaults)}
          className="flex w-full items-center justify-between p-3 text-left"
        >
          <div className="flex items-center gap-2">
            <AdjustmentsHorizontalIcon className="h-4 w-4 text-zinc-500" />
            <span className="text-sm font-medium text-zinc-900 dark:text-white">
              {t('projects.creation.wizard.step5.defaultParams')}
            </span>
          </div>
          {showDefaults ? (
            <ChevronUpIcon className="h-4 w-4 text-zinc-400" />
          ) : (
            <ChevronDownIcon className="h-4 w-4 text-zinc-400" />
          )}
        </button>

        {showDefaults && (
          <div className="border-t border-zinc-200 p-3 dark:border-zinc-700">
            <div className="grid gap-4 sm:grid-cols-3">
              <div>
                <Label className="text-xs">
                  {t('projects.creation.wizard.step5.temperature')}:{' '}
                  {generationParameters.temperature}
                </Label>
                <input
                  type="range"
                  min="0"
                  max="2"
                  step="0.1"
                  value={generationParameters.temperature}
                  onChange={(e) =>
                    onGenerationParametersChange({
                      ...generationParameters,
                      temperature: parseFloat(e.target.value),
                    })
                  }
                  className="mt-1 w-full accent-emerald-600"
                />
              </div>
              <div>
                <Label className="text-xs">
                  {t('projects.creation.wizard.step5.maxTokens')}
                </Label>
                <Input
                  type="number"
                  min={1}
                  max={32768}
                  value={generationParameters.max_tokens}
                  onChange={(e) =>
                    onGenerationParametersChange({
                      ...generationParameters,
                      max_tokens: parseInt(e.target.value) || 4096,
                    })
                  }
                  className="mt-1 text-sm"
                />
              </div>
              <div>
                <Label className="text-xs">
                  {t('projects.creation.wizard.step5.batchSize')}
                </Label>
                <Input
                  type="number"
                  min={1}
                  max={50}
                  value={generationParameters.batch_size}
                  onChange={(e) =>
                    onGenerationParametersChange({
                      ...generationParameters,
                      batch_size: parseInt(e.target.value) || 10,
                    })
                  }
                  className="mt-1 text-sm"
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
