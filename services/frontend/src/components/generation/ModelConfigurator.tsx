'use client'

import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { Input } from '@/components/shared/Input'
import { Label } from '@/components/shared/Label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { api } from '@/lib/api'
import { apiClient } from '@/lib/api/client'
import { Project } from '@/types/labelStudio'
import {
  AdjustmentsHorizontalIcon,
  CheckIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  CpuChipIcon,
  DocumentTextIcon,
  ExclamationTriangleIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline'
import { useEffect, useState } from 'react'

interface ReasoningConfig {
  parameter: string
  type: 'select' | 'number' | 'toggle'
  values?: string[]
  min?: number
  max?: number
  default: string | number | boolean
  label: string
}

interface AvailableModel {
  id: string
  name: string
  description: string
  provider: string
  model_type: string
  capabilities: string[]
  config_schema: any
  default_config: any
  parameter_constraints?: {
    temperature?: {
      supported: boolean
      required_value?: number
      default?: number
      min?: number
      max?: number
      reason?: string
    }
    max_tokens?: {
      default: number
    }
    unsupported_params?: string[]
    reproducibility_impact?: string
    benchmark_notes?: string
  } | null
  is_active: boolean
  created_at: string | null
  updated_at: string | null
}

// Reasoning/thinking config is now served from backend default_config.reasoning_config.
// No hardcoded fallback map needed.

interface ModelConfiguratorProps {
  project: Project
  onConfigUpdate: (config: any) => void
  onStartGeneration: () => void
}

export function ModelConfigurator({
  project,
  onConfigUpdate,
  onStartGeneration,
}: ModelConfiguratorProps) {
  const { addToast } = useToast()
  const { t } = useI18n()
  const [selectedModels, setSelectedModels] = useState<string[]>([])
  const [modelConfigs, setModelConfigs] = useState<Record<string, any>>({})
  const [systemPrompt, setSystemPrompt] = useState('')
  const [instructionPrompt, setInstructionPrompt] = useState('')
  const [temperature, setTemperature] = useState(0)
  const [maxTokens, setMaxTokens] = useState(1500)
  const [batchSize, setBatchSize] = useState(10)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [presentationMode, setPresentationMode] = useState('auto')
  const [isSaving, setIsSaving] = useState(false)
  const [availableModels, setAvailableModels] = useState<AvailableModel[]>([])
  const [modelsLoading, setModelsLoading] = useState(true)

  // Load existing configuration
  useEffect(() => {
    if (project.generation_config?.selected_configuration) {
      const config = project.generation_config.selected_configuration
      setSelectedModels(config.models || [])
      setSystemPrompt(config.prompts?.system || '')
      setInstructionPrompt(config.prompts?.instruction || '')
      setTemperature(config.parameters?.temperature ?? 0)
      setMaxTokens(config.parameters?.max_tokens || 1500)
      setBatchSize(config.parameters?.batch_size || 10)
      setPresentationMode(config.presentation_mode || 'auto')
      setModelConfigs(config.model_configs || {})
    } else if (project.llm_model_ids && project.llm_model_ids.length > 0) {
      // Load models from project detail page selection
      setSelectedModels(project.llm_model_ids)
      // Set default prompts if not already set
      setSystemPrompt(
        'You are an expert annotator. Follow the instructions carefully.'
      )
      setInstructionPrompt('Please complete the following annotation task.')
    }
  }, [project])

  // Fetch available models (only models with valid API keys)
  useEffect(() => {
    const fetchModels = async () => {
      try {
        setModelsLoading(true)
        const models = await api.getAvailableModels()
        setAvailableModels(models)
      } catch (error) {
        console.error('Failed to fetch available models:', error)
        setAvailableModels([])
      } finally {
        setModelsLoading(false)
      }
    }

    fetchModels()
  }, [])

  const toggleModel = (modelId: string) => {
    setSelectedModels((prev) =>
      prev.includes(modelId)
        ? prev.filter((id) => id !== modelId)
        : [...prev, modelId]
    )
  }

  const getReasoningConfig = (modelId: string, model?: AvailableModel): ReasoningConfig | undefined => {
    if (model?.default_config?.reasoning_config) {
      return model.default_config.reasoning_config as ReasoningConfig
    }
    return undefined
  }

  const updateModelConfig = (modelId: string, key: string, value: any) => {
    setModelConfigs((prev) => ({
      ...prev,
      [modelId]: {
        ...prev[modelId],
        [key]: value,
      },
    }))
  }

  const saveConfiguration = async () => {
    if (selectedModels.length === 0) {
      addToast(t('toasts.generation.selectModel'), 'error')
      return
    }

    setIsSaving(true)

    const configuration = {
      detected_data_types: project.generation_config?.detected_data_types || [],
      available_options: project.generation_config?.available_options || {
        models: {},
        presentation_modes: ['label_config', 'template', 'raw_json', 'auto'],
      },
      selected_configuration: {
        models: selectedModels,
        prompts: {
          system:
            systemPrompt ||
            'You are an expert annotator. Follow the instructions carefully and provide accurate, consistent annotations.',
          instruction:
            instructionPrompt ||
            'Please complete the following annotation task:',
        },
        parameters: {
          temperature,
          max_tokens: maxTokens,
          batch_size: batchSize,
        },
        presentation_mode: presentationMode,
        field_mappings: {},
        model_configs: modelConfigs,
      },
      last_updated: new Date().toISOString(),
    }

    try {
      await apiClient.put(
        `/projects/${project.id}/generation-config`,
        configuration
      )
      addToast(t('toasts.generation.configSaved'), 'success')
      onConfigUpdate(configuration)
    } catch (error: any) {
      addToast(
        error.response?.data?.detail || t('toasts.error.saveFailed'),
        'error'
      )
    } finally {
      setIsSaving(false)
    }
  }

  const canStartGeneration = selectedModels.length > 0

  return (
    <div className="space-y-6">
      {/* Model Selection */}
      <Card>
        <div className="p-6">
          <h3 className="mb-4 flex items-center space-x-2 text-lg font-medium">
            <CpuChipIcon className="h-5 w-5" />
            <span>{t('generation.configurator.selectModels')}</span>
          </h3>

          <div className="space-y-3">
            {modelsLoading ? (
              <div className="flex items-center justify-center py-8">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-300 border-t-emerald-500" />
                <span className="ml-3 text-sm text-zinc-500">
                  {t('generation.configurator.loadingModels', 'Loading available models...')}
                </span>
              </div>
            ) : availableModels.length === 0 ? (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-900/20">
                <div className="flex items-center space-x-2">
                  <ExclamationTriangleIcon className="h-5 w-5 text-amber-500" />
                  <p className="text-sm text-amber-700 dark:text-amber-400">
                    {t('generation.configurator.noModelsAvailable', 'No models available. Configure API keys in your profile settings to enable models.')}
                  </p>
                </div>
              </div>
            ) : (
              availableModels.map((model) => {
                const isSelected = selectedModels.includes(model.id)
                const reasoningConfig = getReasoningConfig(model.id, model)

                return (
                  <div
                    key={model.id}
                    className={`relative rounded-lg border p-4 transition-all ${
                      isSelected
                        ? 'border-emerald-500 bg-emerald-50 dark:border-emerald-400 dark:bg-emerald-900/20'
                        : 'border-zinc-200 hover:border-zinc-300 dark:border-zinc-700 dark:hover:border-zinc-600'
                    } cursor-pointer`}
                    onClick={() => toggleModel(model.id)}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center space-x-2">
                          <h4 className="font-medium text-zinc-900 dark:text-white">
                            {model.name}
                          </h4>
                          <span className="rounded-full bg-zinc-200 px-2 py-0.5 text-xs text-zinc-600 dark:bg-zinc-700 dark:text-zinc-400">
                            {model.provider}
                          </span>
                          {reasoningConfig && (
                            <span className="flex items-center space-x-1 rounded-full bg-purple-100 px-2 py-0.5 text-xs text-purple-700 dark:bg-purple-900/30 dark:text-purple-400">
                              <SparklesIcon className="h-3 w-3" />
                              <span>{t('generation.thinkingCapable', 'Thinking')}</span>
                            </span>
                          )}
                        </div>
                        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                          {model.description}
                        </p>

                        {/* Per-model settings (when selected) */}
                        {isSelected && (
                          <div
                            className="mt-3 space-y-3 border-t border-emerald-200 pt-3 dark:border-emerald-800"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {/* Max Tokens */}
                            <div className="flex items-center gap-3">
                              <Label className="min-w-24 text-xs text-zinc-600 dark:text-zinc-400">
                                {t('generation.maxTokens', 'Max Tokens')}
                              </Label>
                              <Input
                                type="number"
                                min="100"
                                max="16000"
                                placeholder={maxTokens.toString()}
                                value={modelConfigs[model.id]?.max_tokens || ''}
                                onChange={(e) =>
                                  updateModelConfig(
                                    model.id,
                                    'max_tokens',
                                    e.target.value ? parseInt(e.target.value) : undefined
                                  )
                                }
                                className="h-8 w-28 text-sm"
                              />
                              <span className="text-xs text-zinc-500">
                                {t('generation.defaultLabel', 'Default')}: {maxTokens}
                              </span>
                            </div>

                            {/* Reasoning/Thinking Config */}
                            {reasoningConfig && (
                              <div className="flex items-center gap-3">
                                <Label className="min-w-24 text-xs text-zinc-600 dark:text-zinc-400">
                                  {t(reasoningConfig.label)}
                                </Label>
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
                                    <SelectTrigger className="h-8 w-28 text-sm">
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
                                {reasoningConfig.type === 'number' && (
                                  <Input
                                    type="number"
                                    min={reasoningConfig.min}
                                    max={reasoningConfig.max}
                                    placeholder={reasoningConfig.default.toString()}
                                    value={
                                      modelConfigs[model.id]?.[reasoningConfig.parameter] || ''
                                    }
                                    onChange={(e) =>
                                      updateModelConfig(
                                        model.id,
                                        reasoningConfig.parameter,
                                        e.target.value ? parseInt(e.target.value) : undefined
                                      )
                                    }
                                    className="h-8 w-28 text-sm"
                                  />
                                )}
                                {reasoningConfig.type === 'toggle' && (
                                  <label className="flex cursor-pointer items-center gap-2">
                                    <input
                                      type="checkbox"
                                      checked={
                                        modelConfigs[model.id]?.[reasoningConfig.parameter] ??
                                        reasoningConfig.default
                                      }
                                      onChange={(e) =>
                                        updateModelConfig(
                                          model.id,
                                          reasoningConfig.parameter,
                                          e.target.checked
                                        )
                                      }
                                      className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500"
                                    />
                                    <span className="text-xs text-zinc-600 dark:text-zinc-400">
                                      {t('generation.enabled', 'Enabled')}
                                    </span>
                                  </label>
                                )}
                              </div>
                            )}
                          </div>
                        )}
                      </div>

                      {isSelected && (
                        <div className="rounded-full bg-emerald-500 p-1 text-white">
                          <CheckIcon className="h-4 w-4" />
                        </div>
                      )}
                    </div>
                  </div>
                )
              })
            )}
          </div>

          {!modelsLoading && availableModels.length > 0 && selectedModels.length === 0 && (
            <p className="mt-4 text-sm text-zinc-500">
              {t('generation.configurator.noModelsHint')}
            </p>
          )}
        </div>
      </Card>

      {/* Prompts Configuration */}
      <Card>
        <div className="p-6">
          <h3 className="mb-4 flex items-center space-x-2 text-lg font-medium">
            <DocumentTextIcon className="h-5 w-5" />
            <span>{t('generation.configurator.prompts')}</span>
          </h3>

          <div className="space-y-4">
            <div>
              <Label htmlFor="system-prompt">{t('generation.configurator.systemPrompt')}</Label>
              <textarea
                id="system-prompt"
                className="mt-1 w-full rounded-md border border-zinc-300 p-3 text-sm dark:border-zinc-700 dark:bg-zinc-800"
                rows={3}
                value={systemPrompt}
                onChange={(e) => setSystemPrompt(e.target.value)}
                placeholder={t('generation.configurator.systemPromptPlaceholder')}
              />
            </div>

            <div>
              <Label htmlFor="instruction-prompt">{t('generation.configurator.instructionPrompt')}</Label>
              <textarea
                id="instruction-prompt"
                className="mt-1 w-full rounded-md border border-zinc-300 p-3 text-sm dark:border-zinc-700 dark:bg-zinc-800"
                rows={3}
                value={instructionPrompt}
                onChange={(e) => setInstructionPrompt(e.target.value)}
                placeholder={t('generation.configurator.instructionPromptPlaceholder')}
              />
            </div>
          </div>
        </div>
      </Card>

      {/* Advanced Settings */}
      <Card>
        <div className="p-6">
          <button
            className="flex w-full items-center justify-between text-left"
            onClick={() => setShowAdvanced(!showAdvanced)}
          >
            <h3 className="flex items-center space-x-2 text-lg font-medium">
              <AdjustmentsHorizontalIcon className="h-5 w-5" />
              <span>{t('generation.configurator.advancedSettings')}</span>
            </h3>
            {showAdvanced ? (
              <ChevronUpIcon className="h-5 w-5 text-zinc-500" />
            ) : (
              <ChevronDownIcon className="h-5 w-5 text-zinc-500" />
            )}
          </button>

          {showAdvanced && (
            <div className="mt-6 space-y-4">
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <div>
                  <Label htmlFor="temperature">
                    {t('generation.configurator.temperature')}: {temperature}
                  </Label>
                  <input
                    id="temperature"
                    type="range"
                    min="0"
                    max="2"
                    step="0.1"
                    value={temperature}
                    onChange={(e) => setTemperature(parseFloat(e.target.value))}
                    className="mt-2 w-full"
                  />
                </div>

                <div>
                  <Label htmlFor="max-tokens">{t('generation.configurator.maxTokens')}</Label>
                  <Input
                    id="max-tokens"
                    type="number"
                    min="1"
                    max="4000"
                    value={maxTokens}
                    onChange={(e) => setMaxTokens(parseInt(e.target.value))}
                  />
                </div>

                <div>
                  <Label htmlFor="batch-size">{t('generation.configurator.batchSize')}</Label>
                  <Input
                    id="batch-size"
                    type="number"
                    min="1"
                    max="50"
                    value={batchSize}
                    onChange={(e) => setBatchSize(parseInt(e.target.value))}
                  />
                </div>
              </div>

              <div>
                <Label htmlFor="presentation-mode">{t('generation.configurator.presentationMode')}</Label>
                <Select
                  value={presentationMode}
                  onValueChange={setPresentationMode}
                  displayValue={
                    presentationMode === 'auto' ? t('generation.configurator.autoDetect') :
                    presentationMode === 'label_config' ? t('generation.configurator.useLabelConfig') :
                    presentationMode === 'template' ? t('generation.configurator.templateMode') :
                    presentationMode === 'raw_json' ? t('generation.configurator.rawJson') :
                    undefined
                  }
                >
                  <SelectTrigger className="mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">{t('generation.configurator.autoDetect')}</SelectItem>
                    <SelectItem value="label_config">{t('generation.configurator.useLabelConfig')}</SelectItem>
                    <SelectItem value="template">{t('generation.configurator.templateMode')}</SelectItem>
                    <SelectItem value="raw_json">{t('generation.configurator.rawJson')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}
        </div>
      </Card>

      {/* Action Buttons */}
      <div className="flex justify-end space-x-3">
        <Button
          variant="outline"
          onClick={saveConfiguration}
          disabled={isSaving || selectedModels.length === 0}
        >
          {isSaving ? t('generation.configurator.saving') : t('generation.configurator.saveConfiguration')}
        </Button>

        <Button
          variant="primary"
          onClick={onStartGeneration}
          disabled={!canStartGeneration}
        >
          <SparklesIcon className="mr-2 h-4 w-4" />
          {t('generation.configurator.startGeneration')}
        </Button>
      </div>
    </div>
  )
}
