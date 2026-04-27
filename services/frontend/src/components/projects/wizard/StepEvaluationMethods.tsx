'use client'

import { Alert } from '@/components/shared/Alert'
import { Badge } from '@/components/shared/Badge'
import { Input } from '@/components/shared/Input'
import { Label } from '@/components/shared/Label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { useI18n } from '@/contexts/I18nContext'
import {
  EvaluationConfig,
  generateEvaluationId,
  GROUPED_METRICS,
  METRIC_DEFINITIONS,
} from '@/lib/api/evaluation-types'
import { OutputField } from '@/lib/labelConfig/fieldExtractor'
import { useModels } from '@/hooks/useModels'
import { ChevronDownIcon, ChevronUpIcon } from '@heroicons/react/24/outline'
import { useState } from 'react'

interface StepEvaluationMethodsProps {
  evaluationConfigs: EvaluationConfig[]
  onEvaluationConfigsChange: (configs: EvaluationConfig[]) => void
  immediateEvaluationEnabled: boolean
  onImmediateEvaluationChange: (val: boolean) => void
  annotationFields: OutputField[]
  dataColumns: string[]
  selectedModelIds: string[]
}

const LLM_JUDGE_METRICS = new Set([
  'llm_judge_classic',
  'llm_judge_custom',
  'llm_judge_falloesung',
])

export function StepEvaluationMethods({
  evaluationConfigs,
  onEvaluationConfigsChange,
  immediateEvaluationEnabled,
  onImmediateEvaluationChange,
  annotationFields,
  dataColumns,
  selectedModelIds,
}: StepEvaluationMethodsProps) {
  const { t } = useI18n()
  const { models } = useModels()
  const [expandedMetric, setExpandedMetric] = useState<string | null>(null)

  const selectedMetrics = new Set(evaluationConfigs.map((c) => c.metric))

  // Build prediction field options from label_config output fields
  const predictionOptions = [
    { value: '__all_model__', label: t('projects.creation.wizard.step7.allModelOutputs') },
    ...annotationFields.map((f) => ({
      value: `model:${f.name}`,
      label: `model:${f.name}`,
    })),
  ]

  // Build reference field options
  const referenceOptions = [
    ...annotationFields.map((f) => ({
      value: `human:${f.name}`,
      label: `${f.name} (${f.type})`,
    })),
    ...dataColumns.map((col) => ({
      value: col,
      label: `${col} (data)`,
    })),
  ]

  const defaultPrediction =
    predictionOptions.length > 0 ? predictionOptions[0].value : ''
  const defaultReference =
    referenceOptions.length > 0 ? referenceOptions[0].value : ''

  const toggleMetric = (metricKey: string) => {
    if (selectedMetrics.has(metricKey)) {
      onEvaluationConfigsChange(
        evaluationConfigs.filter((c) => c.metric !== metricKey)
      )
    } else {
      const def = METRIC_DEFINITIONS[metricKey]
      if (!def) return

      const defaultParams: Record<string, any> = {}
      if (metricKey === 'llm_judge_falloesung') {
        defaultParams.max_tokens = 4096
        defaultParams.score_scale = '0-100'
        defaultParams.answer_type = 'long_text'
      }

      onEvaluationConfigsChange([
        ...evaluationConfigs,
        {
          id: generateEvaluationId(metricKey),
          metric: metricKey,
          display_name: def.display_name,
          prediction_fields: defaultPrediction ? [defaultPrediction] : [],
          reference_fields: defaultReference ? [defaultReference] : [],
          enabled: true,
          metric_parameters: Object.keys(defaultParams).length > 0 ? defaultParams : undefined,
        },
      ])
    }
  }

  const updateConfig = (
    metricKey: string,
    field: keyof EvaluationConfig,
    value: any
  ) => {
    onEvaluationConfigsChange(
      evaluationConfigs.map((c) =>
        c.metric === metricKey ? { ...c, [field]: value } : c
      )
    )
  }

  const hasFieldOptions = predictionOptions.length > 0 || referenceOptions.length > 0
  const isFalloesungSelected = selectedMetrics.has('llm_judge_falloesung')
  const falloesungConfig = evaluationConfigs.find(
    (c) => c.metric === 'llm_judge_falloesung'
  )

  return (
    <div className="space-y-6">
      <div>
        <h2 className="mb-2 text-2xl font-semibold text-zinc-900 dark:text-white">
          {t('projects.creation.wizard.step7.title')}
        </h2>
        <p className="text-zinc-600 dark:text-zinc-400">
          {t('projects.creation.wizard.step7.subtitle')}
        </p>
      </div>

      {/* Immediate evaluation toggle */}
      <div className="flex items-center justify-between">
        <div>
          <Label>{t('projects.creation.wizard.step7.immediateEvaluation')}</Label>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            {t('projects.creation.wizard.step7.immediateEvaluationHint')}
          </p>
        </div>
        <input
          type="checkbox"
          checked={immediateEvaluationEnabled}
          onChange={(e) => onImmediateEvaluationChange(e.target.checked)}
          className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
        />
      </div>

      {/* Selected metrics summary */}
      {evaluationConfigs.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {evaluationConfigs.map((config) => (
            <Badge key={config.id} variant="default" className="text-xs">
              {config.display_name || config.metric}
            </Badge>
          ))}
        </div>
      )}

      {/* Metric groups */}
      <div className="space-y-6">
        {GROUPED_METRICS.map((group) => (
          <div key={group.name}>
            <div className="mb-3">
              <h3 className="text-sm font-semibold text-zinc-900 dark:text-white">
                {group.name}
              </h3>
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                {group.description}
              </p>
            </div>

            <div className="space-y-2">
              {group.metrics.map((metricKey) => {
                const def = METRIC_DEFINITIONS[metricKey]
                if (!def) return null

                const isSelected = selectedMetrics.has(metricKey)
                const config = evaluationConfigs.find(
                  (c) => c.metric === metricKey
                )
                const isExpanded = expandedMetric === metricKey

                return (
                  <div key={metricKey}>
                    <div
                      className="flex items-center justify-between"
                      data-testid={`wizard-metric-${metricKey}`}
                    >
                      <div className="flex-1">
                        <p className="text-sm font-medium text-zinc-900 dark:text-white">
                          {def.display_name}
                        </p>
                        <p className="text-xs text-zinc-500 dark:text-zinc-400">
                          {def.description}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        {isSelected && hasFieldOptions && (
                          <button
                            type="button"
                            onClick={() =>
                              setExpandedMetric(
                                isExpanded ? null : metricKey
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
                          onChange={() => toggleMetric(metricKey)}
                          className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                        />
                      </div>
                    </div>

                    {/* Field mapping (expanded) */}
                    {isSelected && isExpanded && config && hasFieldOptions && (
                      <div className="ml-4 mt-2 space-y-3 rounded-lg border border-zinc-200 p-3 dark:border-zinc-700">
                        {predictionOptions.length > 0 && (
                          <div>
                            <Label className="text-xs">
                              {t('projects.creation.wizard.step7.predictionField')}
                            </Label>
                            <Select
                              value={config.prediction_fields[0] || ''}
                              onValueChange={(val) =>
                                updateConfig(metricKey, 'prediction_fields', [val])
                              }
                            >
                              <SelectTrigger><SelectValue /></SelectTrigger>
                              <SelectContent>
                                {predictionOptions.map((opt) => (
                                  <SelectItem key={opt.value} value={opt.value}>
                                    {opt.label}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                        )}

                        {referenceOptions.length > 0 && (
                          <div>
                            <Label className="text-xs">
                              {t('projects.creation.wizard.step7.referenceField')}
                            </Label>
                            <Select
                              value={config.reference_fields[0] || ''}
                              onValueChange={(val) =>
                                updateConfig(metricKey, 'reference_fields', [val])
                              }
                            >
                              <SelectTrigger><SelectValue /></SelectTrigger>
                              <SelectContent>
                                {referenceOptions.map((opt) => (
                                  <SelectItem key={opt.value} value={opt.value}>
                                    {opt.label}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                        )}

                        {LLM_JUDGE_METRICS.has(metricKey) && models.length > 0 && (
                          <div>
                            <Label className="text-xs">
                              {t('projects.creation.wizard.step7.judgeModel')}
                            </Label>
                            <Select
                              value={(config.metric_parameters as any)?.judge_model || ''}
                              onValueChange={(val) =>
                                updateConfig(metricKey, 'metric_parameters', {
                                  ...config.metric_parameters,
                                  judge_model: val,
                                })
                              }
                            >
                              <SelectTrigger>
                                <SelectValue placeholder={t('projects.creation.wizard.step7.selectJudgeModel')} />
                              </SelectTrigger>
                              <SelectContent>
                                {models.map((m) => (
                                  <SelectItem key={m.id} value={m.id}>
                                    {m.name}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Fallloesung dimensions info + config */}
      {isFalloesungSelected && falloesungConfig && (
        <div className="space-y-4 rounded-lg border border-zinc-200 p-4 dark:border-zinc-700">
          <h3 className="text-sm font-semibold text-zinc-900 dark:text-white">
            {t('projects.creation.wizard.step7.falloesungConfig')}
          </h3>

          {/* Judge model + params */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">
                {t('projects.creation.wizard.step7.judgeModel')}
              </Label>
              <Select
                value={(falloesungConfig.metric_parameters as any)?.judge_model || ''}
                onValueChange={(val) =>
                  updateConfig('llm_judge_falloesung', 'metric_parameters', {
                    ...falloesungConfig.metric_parameters,
                    judge_model: val,
                  })
                }
              >
                <SelectTrigger><SelectValue placeholder={t('projects.creation.wizard.step7.selectJudgeModel')} /></SelectTrigger>
                <SelectContent>
                  {models.map((m) => (
                    <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">
                {t('projects.creation.wizard.step7.maxTokens')}
              </Label>
              <Input
                type="number"
                min={1024}
                max={8192}
                step={256}
                value={(falloesungConfig.metric_parameters as any)?.max_tokens || 4096}
                onChange={(e) =>
                  updateConfig('llm_judge_falloesung', 'metric_parameters', {
                    ...falloesungConfig.metric_parameters,
                    max_tokens: parseInt(e.target.value) || 4096,
                  })
                }
                className="text-sm"
              />
            </div>
          </div>

          {/* Prediction + Reference fields */}
          <div className="grid grid-cols-2 gap-3">
            {predictionOptions.length > 0 && (
              <div>
                <Label className="text-xs">
                  {t('projects.creation.wizard.step7.predictionField')}
                </Label>
                <Select
                  value={falloesungConfig.prediction_fields[0] || ''}
                  onValueChange={(val) =>
                    updateConfig('llm_judge_falloesung', 'prediction_fields', [val])
                  }
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {predictionOptions.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            {referenceOptions.length > 0 && (
              <div>
                <Label className="text-xs">
                  {t('projects.creation.wizard.step7.referenceField')}
                </Label>
                <Select
                  value={falloesungConfig.reference_fields[0] || ''}
                  onValueChange={(val) =>
                    updateConfig('llm_judge_falloesung', 'reference_fields', [val])
                  }
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {referenceOptions.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
        </div>
      )}

      {!hasFieldOptions && (
        <Alert variant="info">
          <p className="text-sm">
            {t('projects.creation.wizard.step7.noFieldsNote')}
          </p>
        </Alert>
      )}

      <Alert variant="info">
        <p className="text-sm">
          {t('projects.creation.wizard.step7.advancedNote')}
        </p>
      </Alert>
    </div>
  )
}
