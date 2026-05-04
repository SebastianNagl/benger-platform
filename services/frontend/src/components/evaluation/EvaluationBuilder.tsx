/**
 * EvaluationBuilder Component
 *
 * Wizard-style UI for configuring evaluations.
 * Supports N:M field mappings where multiple prediction fields can be
 * evaluated against multiple reference fields with different metrics.
 *
 * Best practices incorporated from industry research:
 * - Declarative configuration for reproducibility
 * - Live preview during configuration
 * - Per-metric parameters with sensible defaults
 * - Multi-reference aggregation support
 * - Clear validation feedback
 *
 * Issue #483 - Phase 8: Multi-Field Evaluation Mapping
 */

'use client'

import { Badge } from '@/components/shared/Badge'
import { Button } from '@/components/shared/Button'
import { Checkbox } from '@/components/shared/Checkbox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { api } from '@/lib/api'
import { TemperatureInput } from '@/lib/evaluation/TemperatureInput'
import { useJudgeModelHelpers } from '@/lib/evaluation/judgeModelHelpers'
import { getMetricEditor } from '@/lib/extensions/metricEditors'
import {
  CustomCriteriaDefinition,
  DEFAULT_PROMPT_TEMPLATES,
  FIELD_SPECIFIERS,
  HUMAN_FIELD_PREFIX,
  MODEL_FIELD_PREFIX,
  generateEvaluationId,
  getDimensionDisplayName,
  getFieldDisplayName,
  getGroupedMetrics,
  getMetricDefinitions,
  LLM_JUDGE_DIMENSIONS,
  LLM_JUDGE_TEMPLATES,
  type AvailableEvaluationFields,
  type FieldTypeInfo,
  type EvaluationConfig,
} from '@/lib/api/evaluation-types'
import {
  CheckIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  InformationCircleIcon,
  PencilIcon,
  PlayIcon,
  PlusIcon,
  TrashIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { EvaluationControlModal } from './EvaluationControlModal'
import { FieldMappingEditor } from './FieldMappingEditor'

interface EvaluationBuilderProps {
  projectId: string
  availableFields: AvailableEvaluationFields
  evaluations: EvaluationConfig[]
  onEvaluationsChange: (evaluations: EvaluationConfig[]) => void
  onSave?: () => void
  saving?: boolean
}

type WizardStep =
  | 'metric'
  | 'prediction_fields'
  | 'reference_fields'
  | 'parameters'
  | 'review'

interface NewEvaluationState {
  metric: string
  prediction_fields: string[]
  reference_fields: string[]
  metric_parameters: Record<string, any>
}

const INITIAL_EVALUATION_STATE: NewEvaluationState = {
  metric: '',
  prediction_fields: [],
  reference_fields: [],
  metric_parameters: {},
}

export function EvaluationBuilder({
  projectId,
  availableFields,
  evaluations,
  onEvaluationsChange,
  onSave,
  saving = false,
}: EvaluationBuilderProps) {
  const { t } = useI18n()
  const {
    judgeModels,
    getThinkingConfig,
    getJudgeModelDefaults,
  } = useJudgeModelHelpers()

  const [isAddingNew, setIsAddingNew] = useState(false)
  const [currentStep, setCurrentStep] = useState<WizardStep>('metric')
  const [newEvaluation, setNewEvaluation] = useState<NewEvaluationState>(
    INITIAL_EVALUATION_STATE
  )
  const [editingId, setEditingId] = useState<string | null>(null)
  const [showEvaluationModal, setShowEvaluationModal] = useState(false)
  const { addToast } = useToast()

  const renderTemperatureInput = () => (
    <TemperatureInput
      judgeModelId={newEvaluation.metric_parameters.judge_model || 'gpt-4o'}
      value={newEvaluation.metric_parameters.temperature}
      onChange={(temperature) =>
        setNewEvaluation((prev) => ({
          ...prev,
          metric_parameters: { ...prev.metric_parameters, temperature },
        }))
      }
    />
  )

  // Field types for LLM Judge auto-detection
  const [fieldTypes, setFieldTypes] = useState<Record<string, FieldTypeInfo>>(
    {}
  )
  const [detectedAnswerType, setDetectedAnswerType] = useState<string | null>(
    null
  )

  // Fetch field types for LLM Judge auto-detection
  useEffect(() => {
    const fetchFieldTypes = async () => {
      try {
        const response = await api.get(
          `/evaluations/projects/${projectId}/field-types`
        )
        if (response.data?.field_types) {
          setFieldTypes(response.data.field_types)
        }
      } catch (error) {
        // Field types endpoint not critical - silently fail
        console.debug('Field types not available:', error)
      }
    }
    fetchFieldTypes()
  }, [projectId])

  // Combine model and human fields for prediction selection
  const allPredictionOptions = useMemo(() => {
    const options: {
      value: string
      label: string
      type: 'special' | 'model' | 'human'
    }[] = [
      {
        value: FIELD_SPECIFIERS.ALL_MODEL,
        label: 'All model responses',
        type: 'special',
      },
      {
        value: FIELD_SPECIFIERS.ALL_HUMAN,
        label: 'All human annotations',
        type: 'special',
      },
    ]

    availableFields.model_response_fields.forEach((field) => {
      const prefixed = MODEL_FIELD_PREFIX + field
      options.push({ value: prefixed, label: prefixed, type: 'model' })
    })

    availableFields.human_annotation_fields.forEach((field) => {
      const prefixed = HUMAN_FIELD_PREFIX + field
      options.push({ value: prefixed, label: prefixed, type: 'human' })
    })

    return options
  }, [availableFields])

  // Reference field options
  const referenceOptions = useMemo(() => {
    return availableFields.reference_fields.map((field) => ({
      value: field,
      label: field,
    }))
  }, [availableFields])

  const resetWizard = useCallback(() => {
    setNewEvaluation(INITIAL_EVALUATION_STATE)
    setCurrentStep('metric')
    setIsAddingNew(false)
    setEditingId(null)
  }, [])

  const handleAddEvaluation = useCallback(() => {
    if (!newEvaluation.metric) {
      addToast(t('evaluationBuilder.validation.selectMetric'), 'error')
      return
    }
    if (newEvaluation.prediction_fields.length === 0) {
      addToast(t('evaluationBuilder.validation.selectPrediction'), 'error')
      return
    }
    if (newEvaluation.reference_fields.length === 0) {
      addToast(t('evaluationBuilder.validation.selectReference'), 'error')
      return
    }

    const metricDef = getMetricDefinitions()[newEvaluation.metric]
    const newConfig: EvaluationConfig = {
      id: editingId || generateEvaluationId(newEvaluation.metric),
      metric: newEvaluation.metric,
      display_name: metricDef?.display_name || newEvaluation.metric,
      metric_parameters: newEvaluation.metric_parameters,
      prediction_fields: newEvaluation.prediction_fields,
      reference_fields: newEvaluation.reference_fields,
      enabled: true,
      created_at: new Date().toISOString(),
    }

    if (editingId) {
      // Update existing
      onEvaluationsChange(
        evaluations.map((e) => (e.id === editingId ? newConfig : e))
      )
    } else {
      // Add new
      onEvaluationsChange([...evaluations, newConfig])
    }

    resetWizard()
    addToast(
      editingId
        ? t('evaluationBuilder.toast.updated')
        : t('evaluationBuilder.toast.added'),
      'success'
    )
  }, [
    newEvaluation,
    editingId,
    evaluations,
    onEvaluationsChange,
    resetWizard,
    addToast,
    t,
  ])

  const handleRemoveEvaluation = useCallback(
    (id: string) => {
      onEvaluationsChange(evaluations.filter((e) => e.id !== id))
      addToast(t('evaluationBuilder.toast.deleted'), 'success')
    },
    [evaluations, onEvaluationsChange, addToast, t]
  )

  const handleEditEvaluation = useCallback(
    (evaluation: EvaluationConfig) => {
      setEditingId(evaluation.id)
      setNewEvaluation({
        metric: evaluation.metric,
        prediction_fields: evaluation.prediction_fields,
        reference_fields: evaluation.reference_fields,
        metric_parameters: evaluation.metric_parameters || {},
      })
      setCurrentStep('metric')
      setIsAddingNew(true)
    },
    []
  )

  const handleToggleEnabled = useCallback(
    (id: string) => {
      onEvaluationsChange(
        evaluations.map((e) =>
          e.id === id ? { ...e, enabled: !e.enabled } : e
        )
      )
    },
    [evaluations, onEvaluationsChange]
  )

  const handleFieldToggle = (
    fieldType: 'prediction_fields' | 'reference_fields',
    value: string
  ) => {
    setNewEvaluation((prev) => {
      const currentFields = prev[fieldType]
      const isSelected = currentFields.includes(value)
      const newFields = isSelected
        ? currentFields.filter((f) => f !== value)
        : [...currentFields, value]

      // For LLM Judge: auto-detect answer type on prediction field selection
      if (
        fieldType === 'prediction_fields' &&
        prev.metric === 'llm_judge' &&
        !isSelected
      ) {
        // Strip source prefix to look up field type info
        const baseField = value.startsWith(MODEL_FIELD_PREFIX)
          ? value.substring(MODEL_FIELD_PREFIX.length)
          : value.startsWith(HUMAN_FIELD_PREFIX)
            ? value.substring(HUMAN_FIELD_PREFIX.length)
            : value
        const fieldTypeInfo = fieldTypes[baseField]
        if (fieldTypeInfo) {
          const answerType = fieldTypeInfo.type
          const template = LLM_JUDGE_TEMPLATES[answerType]
          if (template) {
            setDetectedAnswerType(answerType)
            addToast(
              `Detected ${template.name} - auto-selected criteria`,
              'info'
            )
            return {
              ...prev,
              prediction_fields: newFields,
              metric_parameters: {
                ...prev.metric_parameters,
                answer_type: answerType,
                dimensions: template.criteria,
              },
            }
          }
        }
      }

      return {
        ...prev,
        [fieldType]: newFields,
      }
    })
  }

  const handleMetricSelect = (metric: string) => {
    setNewEvaluation((prev) => ({
      ...prev,
      metric,
      metric_parameters: getDefaultParameters(metric),
    }))
  }

  const getDefaultParameters = (metric: string): Record<string, any> => {
    // LLM Judge Classic: predefined dimensions - all selected by default
    if (metric === 'llm_judge_classic') {
      return {
        dimensions: ['helpfulness', 'correctness', 'fluency', 'coherence', 'relevance', 'safety', 'accuracy'],
        answer_type: null,
        custom_criteria: {},
        custom_prompt_template: '',
        field_mappings: {},
      }
    }

    // LLM Judge Custom: empty config for full user control
    if (metric === 'llm_judge_custom') {
      return {
        dimensions: [],
        answer_type: null,
        custom_criteria: {},
        custom_prompt_template: '',
        field_mappings: {},
      }
    }

    const def = getMetricDefinitions()[metric]
    if (!def) return {}

    // Extended metrics may declare default_parameters at registration time
    // (e.g. Falllösung's max_tokens / score_scale / answer_type). Take those
    // as the base, then layer parameter_schema defaults on top.
    const defaults: Record<string, any> = def.default_parameters
      ? { ...def.default_parameters }
      : {}

    if (def.parameter_schema) {
      Object.entries(def.parameter_schema).forEach(([key, schema]) => {
        if ('default' in (schema as any) && !(key in defaults)) {
          defaults[key] = (schema as any).default
        }
      })
    }
    return defaults
  }

  const canProceed = (): boolean => {
    switch (currentStep) {
      case 'metric':
        return !!newEvaluation.metric
      case 'prediction_fields':
        return newEvaluation.prediction_fields.length > 0
      case 'reference_fields':
        return newEvaluation.reference_fields.length > 0
      case 'parameters':
        // Classic LLM Judge: require at least one dimension
        if (newEvaluation.metric === 'llm_judge_classic') {
          const dimensions = newEvaluation.metric_parameters.dimensions || []
          const customCriteria = newEvaluation.metric_parameters.custom_criteria || {}
          return dimensions.length > 0 || Object.keys(customCriteria).length > 0
        }
        // Custom LLM Judge: require either custom prompt OR custom criteria
        if (newEvaluation.metric === 'llm_judge_custom') {
          const customPrompt = newEvaluation.metric_parameters.custom_prompt_template || ''
          const customCriteria = newEvaluation.metric_parameters.custom_criteria || {}
          return customPrompt.trim().length > 0 || Object.keys(customCriteria).length > 0
        }
        return true
      case 'review':
        return true
      default:
        return false
    }
  }

  const getStepNumber = (step: WizardStep): number => {
    const steps: WizardStep[] = [
      'metric',
      'prediction_fields',
      'reference_fields',
      'parameters',
      'review',
    ]
    return steps.indexOf(step) + 1
  }

  const goToNextStep = () => {
    const steps: WizardStep[] = [
      'metric',
      'prediction_fields',
      'reference_fields',
      'parameters',
      'review',
    ]
    const currentIndex = steps.indexOf(currentStep)

    // Skip parameters step if metric doesn't support parameters
    if (currentStep === 'reference_fields') {
      const metricDef = getMetricDefinitions()[newEvaluation.metric]
      if (!metricDef?.supports_parameters) {
        setCurrentStep('review')
        return
      }
    }

    if (currentIndex < steps.length - 1) {
      setCurrentStep(steps[currentIndex + 1])
    }
  }

  const goToPreviousStep = () => {
    const steps: WizardStep[] = [
      'metric',
      'prediction_fields',
      'reference_fields',
      'parameters',
      'review',
    ]
    const currentIndex = steps.indexOf(currentStep)

    // Skip parameters step if metric doesn't support parameters
    if (currentStep === 'review') {
      const metricDef = getMetricDefinitions()[newEvaluation.metric]
      if (!metricDef?.supports_parameters) {
        setCurrentStep('reference_fields')
        return
      }
    }

    if (currentIndex > 0) {
      setCurrentStep(steps[currentIndex - 1])
    }
  }

  const renderWizardStep = () => {
    switch (currentStep) {
      case 'metric':
        return (
          <div className="space-y-4">
            <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              {t('evaluationBuilder.steps.metric.title')}
            </h4>
            <p className="text-xs text-gray-500">
              {t('evaluationBuilder.steps.metric.description')}
            </p>
            <div className="max-h-[400px] space-y-3 overflow-y-auto">
              {getGroupedMetrics().map((group) => (
                <div
                  key={group.name}
                  className="rounded-lg border p-3 dark:border-gray-700"
                >
                  <h5 className="mb-2 text-xs font-medium text-gray-700 dark:text-gray-300">
                    {group.name}
                  </h5>
                  <p className="mb-2 text-xs text-gray-500">
                    {group.description}
                  </p>
                  <div className="space-y-1">
                    {group.metrics.map((metric) => {
                      const def = getMetricDefinitions()[metric]
                      if (!def) return null
                      const isSelected = newEvaluation.metric === metric

                      return (
                        <button
                          key={metric}
                          onClick={() => handleMetricSelect(metric)}
                          data-testid={`metric-button-${metric}`}
                          className={`flex w-full items-center justify-between rounded px-2 py-1.5 text-left transition-colors ${
                            isSelected
                              ? 'bg-emerald-100 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-100'
                              : 'hover:bg-gray-100 dark:hover:bg-gray-800'
                          }`}
                        >
                          <span className="text-sm">
                            {def.display_name}
                          </span>
                          {isSelected && (
                            <svg className="h-4 w-4 text-emerald-600 dark:text-emerald-400" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                            </svg>
                          )}
                        </button>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )

      case 'prediction_fields':
        return (
          <div className="space-y-4">
            <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              {t('evaluationBuilder.steps.predictionFields.title')}
            </h4>
            <p className="text-xs text-gray-500">
              {t('evaluationBuilder.steps.predictionFields.description')}
            </p>
            <div className="space-y-2">
              {/* Special selectors */}
              <div className="mb-3 border-b pb-3 dark:border-gray-700">
                <p className="mb-2 text-xs font-medium text-gray-600 dark:text-gray-400">
                  {t('evaluationBuilder.fields.bulkSelection')}
                </p>
                {allPredictionOptions
                  .filter((opt) => opt.type === 'special')
                  .map((opt) => (
                    <label
                      key={opt.value}
                      className="flex cursor-pointer items-center gap-2 rounded p-2 hover:bg-gray-50 dark:hover:bg-gray-800"
                    >
                      <Checkbox
                        checked={newEvaluation.prediction_fields.includes(
                          opt.value
                        )}
                        onChange={() =>
                          handleFieldToggle('prediction_fields', opt.value)
                        }
                      />
                      <span className="text-sm font-medium text-emerald-600 dark:text-emerald-400">
                        {opt.label}
                      </span>
                    </label>
                  ))}
              </div>

              {/* Model response fields */}
              {availableFields.model_response_fields.length > 0 && (
                <div className="mb-3">
                  <p className="mb-2 text-xs font-medium text-gray-600 dark:text-gray-400">
                    {t('evaluationBuilder.fields.modelResponseFields')}
                  </p>
                  {availableFields.model_response_fields.map((field) => {
                    const prefixed = MODEL_FIELD_PREFIX + field
                    return (
                      <label
                        key={prefixed}
                        className="flex cursor-pointer items-center gap-2 rounded p-2 hover:bg-gray-50 dark:hover:bg-gray-800"
                      >
                        <Checkbox
                          checked={newEvaluation.prediction_fields.includes(
                            prefixed
                          )}
                          onChange={() =>
                            handleFieldToggle('prediction_fields', prefixed)
                          }
                        />
                        <span className="text-sm">{getFieldDisplayName(prefixed)}</span>
                        <Badge variant="secondary" className="text-[10px]">
                          model
                        </Badge>
                      </label>
                    )
                  })}
                </div>
              )}

              {/* Human annotation fields */}
              {availableFields.human_annotation_fields.length > 0 && (
                <div>
                  <p className="mb-2 text-xs font-medium text-gray-600 dark:text-gray-400">
                    {t('evaluationBuilder.fields.humanAnnotationFields')}
                  </p>
                  {availableFields.human_annotation_fields.map((field) => {
                    const prefixed = HUMAN_FIELD_PREFIX + field
                    return (
                      <label
                        key={prefixed}
                        className="flex cursor-pointer items-center gap-2 rounded p-2 hover:bg-gray-50 dark:hover:bg-gray-800"
                      >
                        <Checkbox
                          checked={newEvaluation.prediction_fields.includes(
                            prefixed
                          )}
                          onChange={() =>
                            handleFieldToggle('prediction_fields', prefixed)
                          }
                        />
                        <span className="text-sm">{getFieldDisplayName(prefixed)}</span>
                        <Badge variant="secondary" className="text-[10px]">
                          human
                        </Badge>
                      </label>
                    )
                  })}
                </div>
              )}

              {allPredictionOptions.length === 2 && (
                <p className="py-4 text-xs italic text-gray-500">
                  {t('evaluationBuilder.fields.noFieldsDetected')}
                </p>
              )}
            </div>
          </div>
        )

      case 'reference_fields':
        return (
          <div className="space-y-4">
            <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              {t('evaluationBuilder.steps.referenceFields.title')}
            </h4>
            <p className="text-xs text-gray-500">
              {t('evaluationBuilder.steps.referenceFields.description')}
            </p>
            <div className="space-y-2">
              {referenceOptions.length > 0 ? (
                referenceOptions.map((opt) => (
                  <label
                    key={opt.value}
                    className="flex cursor-pointer items-center gap-2 rounded p-2 hover:bg-gray-50 dark:hover:bg-gray-800"
                  >
                    <Checkbox
                      checked={newEvaluation.reference_fields.includes(
                        opt.value
                      )}
                      onChange={() =>
                        handleFieldToggle('reference_fields', opt.value)
                      }
                    />
                    <span className="text-sm">{opt.label}</span>
                    <Badge variant="default" className="text-[10px]">
                      reference
                    </Badge>
                  </label>
                ))
              ) : (
                <p className="py-4 text-xs italic text-gray-500">
                  {t('evaluationBuilder.fields.noReferenceFields')}
                </p>
              )}
            </div>
            {newEvaluation.reference_fields.length > 1 && (
              <div className="rounded-lg bg-emerald-50 p-3 dark:bg-emerald-900/20">
                <div className="flex items-start gap-2">
                  <InformationCircleIcon className="mt-0.5 h-4 w-4 text-emerald-500" />
                  <div className="text-xs text-emerald-700 dark:text-emerald-300">
                    <strong>
                      {t('evaluationBuilder.fields.multipleReferencesTitle')}
                    </strong>{' '}
                    {t(
                      'evaluationBuilder.fields.multipleReferencesDescription'
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        )

      case 'parameters':
        const metricDef = getMetricDefinitions()[newEvaluation.metric]
        return (
          <div className="space-y-4">
            <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              {t('evaluationBuilder.steps.parameters.title')}
            </h4>
            <p className="text-xs text-gray-500">
              {t('evaluationBuilder.steps.parameters.descriptionWithMetric', {
                metric: metricDef?.display_name || newEvaluation.metric,
              })}
            </p>

            {newEvaluation.metric === 'llm_judge_classic' ? (
              <div className="space-y-4">
                {/* Detected Answer Type Banner */}
                {(detectedAnswerType ||
                  newEvaluation.metric_parameters.answer_type) && (
                  <div className="rounded-lg bg-emerald-50 p-3 dark:bg-emerald-900/20">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <InformationCircleIcon className="h-4 w-4 text-emerald-600" />
                        <span className="text-sm font-medium text-emerald-700 dark:text-emerald-300">
                          Detected:{' '}
                          {LLM_JUDGE_TEMPLATES[
                            newEvaluation.metric_parameters.answer_type ||
                              detectedAnswerType ||
                              'text'
                          ]?.name || 'Free-form Text'}
                        </span>
                      </div>
                      <Badge variant="secondary">
                        {newEvaluation.metric_parameters.answer_type ||
                          detectedAnswerType ||
                          'text'}
                      </Badge>
                    </div>
                    <p className="mt-1 text-xs text-emerald-600 dark:text-emerald-400">
                      {LLM_JUDGE_TEMPLATES[
                        newEvaluation.metric_parameters.answer_type ||
                          detectedAnswerType ||
                          'text'
                      ]?.hint || ''}
                    </p>
                  </div>
                )}

                {/* Answer Type Override */}
                <div>
                  <label className="mb-2 block text-xs font-medium text-gray-700 dark:text-gray-300">
                    {t('evaluationBuilder.parameters.answerType')}{' '}
                    {detectedAnswerType && (
                      <span className="text-gray-400">
                        ({t('evaluationBuilder.parameters.autoDetected')})
                      </span>
                    )}
                  </label>
                  <Select
                    value={
                      newEvaluation.metric_parameters.answer_type ||
                      detectedAnswerType ||
                      'text'
                    }
                    onValueChange={(newType) => {
                      const template = LLM_JUDGE_TEMPLATES[newType]
                      setNewEvaluation((prev) => ({
                        ...prev,
                        metric_parameters: {
                          ...prev.metric_parameters,
                          answer_type: newType,
                          dimensions: template?.criteria || [
                            'helpfulness',
                            'correctness',
                          ],
                        },
                      }))
                    }}
                    displayValue={LLM_JUDGE_TEMPLATES[newEvaluation.metric_parameters.answer_type || detectedAnswerType || 'text']?.name}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select answer type..." />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(LLM_JUDGE_TEMPLATES).map(([key, tmpl]) => (
                        <SelectItem key={key} value={key}>
                          {tmpl.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Judge Model Selection */}
                <div>
                  <label className="mb-2 block text-xs font-medium text-gray-700 dark:text-gray-300">
                    {t('evaluationBuilder.parameters.judgeModel')}
                  </label>
                  <Select
                    value={
                      newEvaluation.metric_parameters.judge_model || 'gpt-4o'
                    }
                    onValueChange={(modelId) => {
                      const defaults = getJudgeModelDefaults(modelId)
                      setNewEvaluation((prev) => ({
                        ...prev,
                        metric_parameters: {
                          ...prev.metric_parameters,
                          judge_model: modelId,
                          // Pre-fill defaults for model-specific requirements
                          temperature: defaults.temperature,
                          max_tokens: defaults.max_tokens,
                        },
                      }))
                    }}
                    displayValue={(() => { const m = judgeModels.find(m => m.id === (newEvaluation.metric_parameters.judge_model || 'gpt-4o')); return m ? `${m.name} (${m.provider})` : undefined })()}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select judge model..." />
                    </SelectTrigger>
                    <SelectContent>
                      {judgeModels.map((model) => (
                        <SelectItem key={model.id} value={model.id}>
                          {model.name} ({model.provider})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Temperature */}
                {renderTemperatureInput()}

                {/* Thinking Budget - for Anthropic/Google models */}
                {getThinkingConfig(
                  newEvaluation.metric_parameters.judge_model || 'gpt-4o'
                )?.type === 'budget' && (
                  <div>
                    <label className="mb-2 flex items-center gap-2 text-xs font-medium text-gray-700 dark:text-gray-300">
                      {t(
                        'evaluationBuilder.parameters.thinkingBudget',
                        'Thinking Budget'
                      )}
                      <span className="rounded bg-purple-100 px-2 py-0.5 text-xs text-purple-700 dark:bg-purple-900/30 dark:text-purple-300">
                        Thinking
                      </span>
                    </label>
                    <input
                      type="number"
                      min={1024}
                      max={128000}
                      value={
                        newEvaluation.metric_parameters.thinking_budget || ''
                      }
                      placeholder={String(
                        getThinkingConfig(
                          newEvaluation.metric_parameters.judge_model || 'gpt-4o'
                        )?.default || 8000
                      )}
                      onChange={(e) =>
                        setNewEvaluation((prev) => ({
                          ...prev,
                          metric_parameters: {
                            ...prev.metric_parameters,
                            thinking_budget: e.target.value
                              ? parseInt(e.target.value)
                              : undefined,
                          },
                        }))
                      }
                      className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800"
                    />
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      {t(
                        'evaluationBuilder.parameters.thinkingBudgetDescription',
                        'Token budget for AI reasoning before generating response'
                      )}
                    </p>
                  </div>
                )}

                {/* Reasoning Effort - for OpenAI o-series */}
                {getThinkingConfig(
                  newEvaluation.metric_parameters.judge_model || 'gpt-4o'
                )?.type === 'effort' && (
                  <div>
                    <label className="mb-2 flex items-center gap-2 text-xs font-medium text-gray-700 dark:text-gray-300">
                      {t(
                        'evaluationBuilder.parameters.reasoningLevel',
                        'Reasoning Level'
                      )}
                      <span className="rounded bg-purple-100 px-2 py-0.5 text-xs text-purple-700 dark:bg-purple-900/30 dark:text-purple-300">
                        Thinking
                      </span>
                    </label>
                    <Select
                      value={
                        newEvaluation.metric_parameters.reasoning_effort ||
                        'medium'
                      }
                      onValueChange={(v) =>
                        setNewEvaluation((prev) => ({
                          ...prev,
                          metric_parameters: {
                            ...prev.metric_parameters,
                            reasoning_effort: v,
                          },
                        }))
                      }
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select reasoning level..." />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="low">
                          {t('evaluationBuilder.parameters.reasoningLow', 'Low')}
                        </SelectItem>
                        <SelectItem value="medium">
                          {t(
                            'evaluationBuilder.parameters.reasoningMedium',
                            'Medium (Default)'
                          )}
                        </SelectItem>
                        <SelectItem value="high">
                          {t(
                            'evaluationBuilder.parameters.reasoningHigh',
                            'High'
                          )}
                        </SelectItem>
                      </SelectContent>
                    </Select>
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      {t(
                        'evaluationBuilder.parameters.reasoningLevelDescription',
                        'How much reasoning the model should use'
                      )}
                    </p>
                  </div>
                )}

                {/* Max Tokens for Judge Response */}
                <div>
                  <label className="mb-2 block text-xs font-medium text-gray-700 dark:text-gray-300">
                    {t('evaluationBuilder.parameters.maxTokens', 'Max Tokens')}
                  </label>
                  <input
                    type="number"
                    min={100}
                    max={4000}
                    value={newEvaluation.metric_parameters.max_tokens || 500}
                    onChange={(e) =>
                      setNewEvaluation((prev) => ({
                        ...prev,
                        metric_parameters: {
                          ...prev.metric_parameters,
                          max_tokens: parseInt(e.target.value) || 500,
                        },
                      }))
                    }
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800"
                  />
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {t(
                      'evaluationBuilder.parameters.maxTokensDescription',
                      'Maximum tokens for judge response (100-4000)'
                    )}
                  </p>
                </div>

              </div>
            ) : newEvaluation.metric === 'llm_judge_custom' ? (
              <div className="space-y-6">
                {/* Custom LLM Judge - Full configuration exposed */}
                <div className="rounded-lg bg-purple-50 p-3 dark:bg-purple-900/20">
                  <div className="flex items-center gap-2">
                    <InformationCircleIcon className="h-4 w-4 text-purple-600 dark:text-purple-400" />
                    <span className="text-sm text-purple-700 dark:text-purple-300">
                      {t('evaluation.customLLMJudge.hint', 'Configure your own evaluation prompt and criteria. Use template variables like {{prediction}} and {{ground_truth}}.')}
                    </span>
                  </div>
                </div>

                {/* Judge Model Selection */}
                <div>
                  <label className="mb-2 block text-xs font-medium text-gray-700 dark:text-gray-300">
                    {t('evaluationBuilder.parameters.judgeModel')}
                  </label>
                  <Select
                    value={
                      newEvaluation.metric_parameters.judge_model || 'gpt-4o'
                    }
                    onValueChange={(modelId) => {
                      const defaults = getJudgeModelDefaults(modelId)
                      setNewEvaluation((prev) => ({
                        ...prev,
                        metric_parameters: {
                          ...prev.metric_parameters,
                          judge_model: modelId,
                          // Pre-fill defaults for model-specific requirements
                          temperature: defaults.temperature,
                          max_tokens: defaults.max_tokens,
                        },
                      }))
                    }}
                    displayValue={(() => { const m = judgeModels.find(m => m.id === (newEvaluation.metric_parameters.judge_model || 'gpt-4o')); return m ? `${m.name} (${m.provider})` : undefined })()}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select judge model..." />
                    </SelectTrigger>
                    <SelectContent>
                      {judgeModels.map((model) => (
                        <SelectItem key={model.id} value={model.id}>
                          {model.name} ({model.provider})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Temperature */}
                {renderTemperatureInput()}

                {/* Thinking Budget - for Anthropic/Google models */}
                {getThinkingConfig(
                  newEvaluation.metric_parameters.judge_model || 'gpt-4o'
                )?.type === 'budget' && (
                  <div>
                    <label className="mb-2 flex items-center gap-2 text-xs font-medium text-gray-700 dark:text-gray-300">
                      {t(
                        'evaluationBuilder.parameters.thinkingBudget',
                        'Thinking Budget'
                      )}
                      <span className="rounded bg-purple-100 px-2 py-0.5 text-xs text-purple-700 dark:bg-purple-900/30 dark:text-purple-300">
                        Thinking
                      </span>
                    </label>
                    <input
                      type="number"
                      min={1024}
                      max={128000}
                      value={
                        newEvaluation.metric_parameters.thinking_budget || ''
                      }
                      placeholder={String(
                        getThinkingConfig(
                          newEvaluation.metric_parameters.judge_model || 'gpt-4o'
                        )?.default || 8000
                      )}
                      onChange={(e) =>
                        setNewEvaluation((prev) => ({
                          ...prev,
                          metric_parameters: {
                            ...prev.metric_parameters,
                            thinking_budget: e.target.value
                              ? parseInt(e.target.value)
                              : undefined,
                          },
                        }))
                      }
                      className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800"
                    />
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      {t(
                        'evaluationBuilder.parameters.thinkingBudgetDescription',
                        'Token budget for AI reasoning before generating response'
                      )}
                    </p>
                  </div>
                )}

                {/* Reasoning Effort - for OpenAI o-series */}
                {getThinkingConfig(
                  newEvaluation.metric_parameters.judge_model || 'gpt-4o'
                )?.type === 'effort' && (
                  <div>
                    <label className="mb-2 flex items-center gap-2 text-xs font-medium text-gray-700 dark:text-gray-300">
                      {t(
                        'evaluationBuilder.parameters.reasoningLevel',
                        'Reasoning Level'
                      )}
                      <span className="rounded bg-purple-100 px-2 py-0.5 text-xs text-purple-700 dark:bg-purple-900/30 dark:text-purple-300">
                        Thinking
                      </span>
                    </label>
                    <Select
                      value={
                        newEvaluation.metric_parameters.reasoning_effort ||
                        'medium'
                      }
                      onValueChange={(v) =>
                        setNewEvaluation((prev) => ({
                          ...prev,
                          metric_parameters: {
                            ...prev.metric_parameters,
                            reasoning_effort: v,
                          },
                        }))
                      }
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select reasoning level..." />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="low">
                          {t('evaluationBuilder.parameters.reasoningLow', 'Low')}
                        </SelectItem>
                        <SelectItem value="medium">
                          {t(
                            'evaluationBuilder.parameters.reasoningMedium',
                            'Medium (Default)'
                          )}
                        </SelectItem>
                        <SelectItem value="high">
                          {t(
                            'evaluationBuilder.parameters.reasoningHigh',
                            'High'
                          )}
                        </SelectItem>
                      </SelectContent>
                    </Select>
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      {t(
                        'evaluationBuilder.parameters.reasoningLevelDescription',
                        'How much reasoning the model should use'
                      )}
                    </p>
                  </div>
                )}

                {/* Max Tokens for Judge Response */}
                <div>
                  <label className="mb-2 block text-xs font-medium text-gray-700 dark:text-gray-300">
                    {t('evaluationBuilder.parameters.maxTokens', 'Max Tokens')}
                  </label>
                  <input
                    type="number"
                    min={100}
                    max={4000}
                    value={newEvaluation.metric_parameters.max_tokens || 500}
                    onChange={(e) =>
                      setNewEvaluation((prev) => ({
                        ...prev,
                        metric_parameters: {
                          ...prev.metric_parameters,
                          max_tokens: parseInt(e.target.value) || 500,
                        },
                      }))
                    }
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800"
                  />
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {t(
                      'evaluationBuilder.parameters.maxTokensDescription',
                      'Maximum tokens for judge response (100-4000)'
                    )}
                  </p>
                </div>

                {/* Score Scale Selection */}
                <div>
                  <label className="mb-2 block text-xs font-medium text-gray-700 dark:text-gray-300">
                    {t('evaluationBuilder.parameters.scoreScale')}
                  </label>
                  <Select
                    value={
                      (newEvaluation.metric_parameters.score_scale as string) || '1-5'
                    }
                    onValueChange={(v) =>
                      setNewEvaluation((prev) => ({
                        ...prev,
                        metric_parameters: {
                          ...prev.metric_parameters,
                          score_scale: v,
                        },
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select score scale..." />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="1-5">1-5 {t('evaluationBuilder.parameters.scoreScaleNormalized')}</SelectItem>
                      <SelectItem value="0-1">0-1 {t('evaluationBuilder.parameters.scoreScaleDirect')}</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {t('evaluationBuilder.parameters.scoreScaleDescription')}
                  </p>
                </div>

                {/* Field Mapping Editor - primary for Custom */}
                <FieldMappingEditor
                  projectId={projectId}
                  value={(newEvaluation.metric_parameters.field_mappings as Record<string, string>) || {}}
                  onChange={(mappings) =>
                    setNewEvaluation((prev) => ({
                      ...prev,
                      metric_parameters: {
                        ...prev.metric_parameters,
                        field_mappings: Object.keys(mappings).length > 0 ? mappings : undefined,
                      },
                    }))
                  }
                />

              </div>
            ) : newEvaluation.metric === 'bleu' ? (
              <div className="space-y-4">
                <div>
                  <label className="mb-2 block text-xs font-medium text-gray-700 dark:text-gray-300">
                    {t('evaluationBuilder.parameters.bleu.maxOrder')}
                  </label>
                  <Select
                    value={(newEvaluation.metric_parameters.max_order || 4).toString()}
                    onValueChange={(v) =>
                      setNewEvaluation((prev) => ({
                        ...prev,
                        metric_parameters: {
                          ...prev.metric_parameters,
                          max_order: parseInt(v),
                        },
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select max order..." />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="1">1 (unigram only)</SelectItem>
                      <SelectItem value="2">2 (up to bigram)</SelectItem>
                      <SelectItem value="3">3 (up to trigram)</SelectItem>
                      <SelectItem value="4">4 (standard BLEU-4)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <label className="mb-2 block text-xs font-medium text-gray-700 dark:text-gray-300">
                    {t('evaluationBuilder.parameters.bleu.smoothing')}
                  </label>
                  <Select
                    value={
                      newEvaluation.metric_parameters.smoothing || 'method1'
                    }
                    onValueChange={(v) =>
                      setNewEvaluation((prev) => ({
                        ...prev,
                        metric_parameters: {
                          ...prev.metric_parameters,
                          smoothing: v,
                        },
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select smoothing method..." />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="method1">Method 1 (add epsilon)</SelectItem>
                      <SelectItem value="method2">Method 2 (add 1)</SelectItem>
                      <SelectItem value="method3">Method 3 (NIST geometric)</SelectItem>
                      <SelectItem value="method4">Method 4 (exponential decay)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            ) : newEvaluation.metric === 'rouge' ? (
              <div className="space-y-4">
                <div>
                  <label className="mb-2 block text-xs font-medium text-gray-700 dark:text-gray-300">
                    {t('evaluationBuilder.parameters.rouge.variant')}
                  </label>
                  <Select
                    value={newEvaluation.metric_parameters.variant || 'rougeL'}
                    onValueChange={(v) =>
                      setNewEvaluation((prev) => ({
                        ...prev,
                        metric_parameters: {
                          ...prev.metric_parameters,
                          variant: v,
                        },
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select ROUGE variant..." />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="rouge1">ROUGE-1 (unigram)</SelectItem>
                      <SelectItem value="rouge2">ROUGE-2 (bigram)</SelectItem>
                      <SelectItem value="rougeL">ROUGE-L (LCS-based)</SelectItem>
                      <SelectItem value="rougeLsum">ROUGE-Lsum (summary level)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex items-center gap-2">
                  <Checkbox
                    checked={
                      newEvaluation.metric_parameters.use_stemmer !== false
                    }
                    onChange={() =>
                      setNewEvaluation((prev) => ({
                        ...prev,
                        metric_parameters: {
                          ...prev.metric_parameters,
                          use_stemmer: !prev.metric_parameters.use_stemmer,
                        },
                      }))
                    }
                  />
                  <label className="text-xs text-gray-700 dark:text-gray-300">
                    {t('evaluationBuilder.parameters.rouge.useStemmer')}
                  </label>
                </div>
              </div>
            ) : newEvaluation.metric === 'meteor' ? (
              <div className="space-y-4">
                <div>
                  <label className="mb-2 block text-xs font-medium text-gray-700 dark:text-gray-300">
                    Alpha (precision weight):{' '}
                    {newEvaluation.metric_parameters.alpha || 0.9}
                  </label>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.1"
                    value={newEvaluation.metric_parameters.alpha || 0.9}
                    onChange={(e) =>
                      setNewEvaluation((prev) => ({
                        ...prev,
                        metric_parameters: {
                          ...prev.metric_parameters,
                          alpha: parseFloat(e.target.value),
                        },
                      }))
                    }
                    className="w-full"
                  />
                </div>
                <div>
                  <label className="mb-2 block text-xs font-medium text-gray-700 dark:text-gray-300">
                    Beta (recall weight):{' '}
                    {newEvaluation.metric_parameters.beta || 3.0}
                  </label>
                  <input
                    type="range"
                    min="0"
                    max="10"
                    step="0.5"
                    value={newEvaluation.metric_parameters.beta || 3.0}
                    onChange={(e) =>
                      setNewEvaluation((prev) => ({
                        ...prev,
                        metric_parameters: {
                          ...prev.metric_parameters,
                          beta: parseFloat(e.target.value),
                        },
                      }))
                    }
                    className="w-full"
                  />
                </div>
                <div>
                  <label className="mb-2 block text-xs font-medium text-gray-700 dark:text-gray-300">
                    Gamma (fragmentation penalty):{' '}
                    {newEvaluation.metric_parameters.gamma || 0.5}
                  </label>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.1"
                    value={newEvaluation.metric_parameters.gamma || 0.5}
                    onChange={(e) =>
                      setNewEvaluation((prev) => ({
                        ...prev,
                        metric_parameters: {
                          ...prev.metric_parameters,
                          gamma: parseFloat(e.target.value),
                        },
                      }))
                    }
                    className="w-full"
                  />
                </div>
              </div>
            ) : newEvaluation.metric === 'chrf' ? (
              <div className="space-y-4">
                <div>
                  <label className="mb-2 block text-xs font-medium text-gray-700 dark:text-gray-300">
                    Character N-gram Order
                  </label>
                  <Select
                    value={(newEvaluation.metric_parameters.char_order || 6).toString()}
                    onValueChange={(v) =>
                      setNewEvaluation((prev) => ({
                        ...prev,
                        metric_parameters: {
                          ...prev.metric_parameters,
                          char_order: parseInt(v),
                        },
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select char order..." />
                    </SelectTrigger>
                    <SelectContent>
                      {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
                        <SelectItem key={n} value={n.toString()}>
                          {n}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <label className="mb-2 block text-xs font-medium text-gray-700 dark:text-gray-300">
                    Word N-gram Order (0 = character-only)
                  </label>
                  <Select
                    value={(newEvaluation.metric_parameters.word_order || 0).toString()}
                    onValueChange={(v) =>
                      setNewEvaluation((prev) => ({
                        ...prev,
                        metric_parameters: {
                          ...prev.metric_parameters,
                          word_order: parseInt(v),
                        },
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select word order..." />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="0">0 (character-level only)</SelectItem>
                      <SelectItem value="1">1 (include unigrams)</SelectItem>
                      <SelectItem value="2">2 (include bigrams)</SelectItem>
                      <SelectItem value="3">3 (include trigrams)</SelectItem>
                      <SelectItem value="4">4 (include 4-grams)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <label className="mb-2 block text-xs font-medium text-gray-700 dark:text-gray-300">
                    Beta (recall weight):{' '}
                    {newEvaluation.metric_parameters.beta || 2}
                  </label>
                  <input
                    type="range"
                    min="1"
                    max="5"
                    step="0.5"
                    value={newEvaluation.metric_parameters.beta || 2}
                    onChange={(e) =>
                      setNewEvaluation((prev) => ({
                        ...prev,
                        metric_parameters: {
                          ...prev.metric_parameters,
                          beta: parseFloat(e.target.value),
                        },
                      }))
                    }
                    className="w-full"
                  />
                </div>
              </div>
            ) : newEvaluation.metric === 'factcc' ? (
              <div>
                <label className="mb-2 block text-xs font-medium text-gray-700 dark:text-gray-300">
                  Factuality Method
                </label>
                <Select
                  value={newEvaluation.metric_parameters.method || 'summac'}
                  onValueChange={(v) =>
                    setNewEvaluation((prev) => ({
                      ...prev,
                      metric_parameters: {
                        ...prev.metric_parameters,
                        method: v,
                      },
                    }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select factuality method..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="summac">SummaC (recommended)</SelectItem>
                    <SelectItem value="factcc">Original FactCC</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            ) : (() => {
              // Last-resort: extended packages may register a per-metric editor
              // (e.g. korrektur_classic / korrektur_falloesung policy fields).
              const ExtendedEditor = getMetricEditor(newEvaluation.metric)
              if (ExtendedEditor) {
                return (
                  <ExtendedEditor
                    parameters={newEvaluation.metric_parameters}
                    onChange={(patch) =>
                      setNewEvaluation((prev) => ({
                        ...prev,
                        metric_parameters: { ...prev.metric_parameters, ...patch },
                      }))
                    }
                  />
                )
              }
              return (
                <p className="py-4 text-xs italic text-gray-500">
                  {t('evaluationBuilder.parameters.defaultParameters')}
                </p>
              )
            })()}
          </div>
        )

      case 'review':
        const reviewMetricDef = getMetricDefinitions()[newEvaluation.metric]
        return (
          <div className="space-y-4">
            <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              {t('evaluationBuilder.steps.review.title')}
            </h4>
            <div className="space-y-3 rounded-lg bg-gray-50 p-4 dark:bg-gray-800">
              <div>
                <span className="text-xs text-gray-500">
                  {t('evaluationBuilder.review.metric')}:
                </span>
                <p className="text-sm font-medium">
                  {reviewMetricDef?.display_name || newEvaluation.metric}
                </p>
              </div>
              <div>
                <span className="text-xs text-gray-500">
                  {t('evaluationBuilder.review.predictionFields')}:
                </span>
                <div className="mt-1 flex flex-wrap gap-1">
                  {newEvaluation.prediction_fields.map((field) => (
                    <Badge key={field} variant="secondary" className="text-xs">
                      {getFieldDisplayName(field)}
                    </Badge>
                  ))}
                </div>
              </div>
              <div>
                <span className="text-xs text-gray-500">
                  {t('evaluationBuilder.review.referenceFields')}:
                </span>
                <div className="mt-1 flex flex-wrap gap-1">
                  {newEvaluation.reference_fields.map((field) => (
                    <Badge key={field} variant="default" className="text-xs">
                      {field}
                    </Badge>
                  ))}
                </div>
              </div>
              {Object.keys(newEvaluation.metric_parameters).length > 0 && (
                <div>
                  <span className="text-xs text-gray-500">
                    {t('evaluationBuilder.review.parameters')}:
                  </span>
                  <pre className="mt-1 overflow-x-auto rounded bg-gray-100 p-2 text-xs dark:bg-gray-700">
                    {JSON.stringify(newEvaluation.metric_parameters, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        )
    }
  }

  return (
    <div className="space-y-4">
      {/* Action Bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Badge variant="secondary" className="text-xs">
            {t('evaluationBuilder.configured', { count: evaluations.length })}
          </Badge>
        </div>
        <Button
          onClick={() => setIsAddingNew(true)}
          className="text-sm"
          disabled={isAddingNew}
          data-testid="add-evaluation-button"
        >
          <PlusIcon className="mr-1 h-4 w-4" />
          {t('evaluationBuilder.addEvaluation')}
        </Button>
      </div>

      {/* Add New Wizard */}
      {isAddingNew && (
        <div className="overflow-hidden rounded-lg border dark:border-gray-700">
          {/* Wizard Header */}
          <div
            className="flex items-center justify-between bg-emerald-50 px-4 py-3 dark:bg-emerald-900/30"
            data-testid="evaluation-wizard-header"
          >
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-emerald-900 dark:text-emerald-100">
                {editingId
                  ? t('evaluationBuilder.editEvaluation')
                  : t('evaluationBuilder.newEvaluation')}
              </span>
              <span
                className="text-xs text-emerald-600 dark:text-emerald-400"
                data-testid="wizard-step-indicator"
              >
                {t('evaluationBuilder.stepOf', {
                  current: getStepNumber(currentStep),
                  total: 5,
                })}
              </span>
            </div>
            <button
              onClick={resetWizard}
              className="text-emerald-600 hover:text-emerald-800 dark:text-emerald-400 dark:hover:text-emerald-200"
            >
              <XMarkIcon className="h-5 w-5" />
            </button>
          </div>

          {/* Wizard Content */}
          <div className="p-4" data-testid="evaluation-wizard-body">
            {renderWizardStep()}
          </div>

          {/* Wizard Footer */}
          <div className="flex justify-between bg-gray-50 px-4 py-3 dark:bg-gray-800">
            <Button
              onClick={goToPreviousStep}
              variant="secondary"
              disabled={currentStep === 'metric'}
              className="text-sm"
              data-testid="wizard-back-button"
            >
              {t('evaluationBuilder.back')}
            </Button>
            <div className="flex gap-2">
              <Button
                onClick={resetWizard}
                variant="secondary"
                className="text-sm"
              >
                {t('evaluationBuilder.cancel')}
              </Button>
              {currentStep === 'review' ? (
                <Button onClick={handleAddEvaluation} className="text-sm">
                  <CheckIcon className="mr-1 h-4 w-4" />
                  {editingId
                    ? t('evaluationBuilder.update')
                    : t('evaluationBuilder.addEvaluation')}
                </Button>
              ) : (
                <Button
                  onClick={goToNextStep}
                  disabled={!canProceed()}
                  className="text-sm"
                  data-testid="wizard-next-button"
                >
                  {t('evaluationBuilder.next')}
                </Button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Configured Evaluations List */}
      {evaluations.length > 0 ? (
        <div className="space-y-3">
          {evaluations.map((evaluation) => {
            const metricDef = getMetricDefinitions()[evaluation.metric]
            return (
              <div
                key={evaluation.id}
                className={`rounded-lg border p-4 dark:border-gray-700 ${
                  !evaluation.enabled ? 'opacity-50' : ''
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="mb-2 flex items-center gap-2">
                      <span className="font-medium text-gray-900 dark:text-gray-100">
                        {evaluation.display_name ||
                          metricDef?.display_name ||
                          evaluation.metric}
                      </span>
                      {!evaluation.enabled && (
                        <Badge variant="secondary" className="text-[10px]">
                          disabled
                        </Badge>
                      )}
                    </div>
                    <div className="space-y-1 text-xs text-gray-500">
                      <div>
                        <span className="font-medium">
                          {t('evaluationBuilder.list.predictions')}
                        </span>{' '}
                        {evaluation.prediction_fields
                          .map(getFieldDisplayName)
                          .join(', ')}
                      </div>
                      <div>
                        <span className="font-medium">
                          {t('evaluationBuilder.list.references')}
                        </span>{' '}
                        {evaluation.reference_fields.join(', ')}
                      </div>
                      {evaluation.metric_parameters &&
                        Object.keys(evaluation.metric_parameters).length >
                          0 && (
                          <div>
                            <span className="font-medium">
                              {t('evaluationBuilder.list.parameters')}
                            </span>{' '}
                            {JSON.stringify(evaluation.metric_parameters)}
                          </div>
                        )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleToggleEnabled(evaluation.id)}
                      className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                      title={evaluation.enabled ? t('common.disable') : t('common.enable')}
                    >
                      <Checkbox
                        checked={evaluation.enabled}
                        onChange={() => {}}
                      />
                    </button>
                    <button
                      onClick={() => handleEditEvaluation(evaluation)}
                      className="text-gray-400 hover:text-emerald-600 dark:hover:text-emerald-400"
                      title={t('common.edit')}
                    >
                      <PencilIcon className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => handleRemoveEvaluation(evaluation.id)}
                      className="text-gray-400 hover:text-red-600 dark:hover:text-red-400"
                      title={t('common.remove')}
                    >
                      <TrashIcon className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      ) : !isAddingNew ? (
        <div className="py-8 text-center text-gray-500">
          <p className="text-sm">{t('evaluationBuilder.emptyState.title')}</p>
          <p className="mt-1 text-xs">
            {t('evaluationBuilder.emptyState.description')}
          </p>
        </div>
      ) : null}

      {/* Run Evaluation Button */}
      {evaluations.length > 0 && (
        <div className="flex flex-col gap-3 border-t pt-4 dark:border-gray-700">
          <div className="flex justify-end gap-2">
            <p className="mr-2 self-center text-xs text-gray-500 dark:text-gray-400">
              {t('evaluationBuilder.runEvaluation.configsWillBeEvaluated', {
                count: evaluations.filter((e) => e.enabled).length,
              })}
            </p>
            <Button
              onClick={() => setShowEvaluationModal(true)}
              disabled={saving}
              className="flex items-center gap-2 text-sm"
            >
              <PlayIcon className="h-4 w-4" />
              {saving
                ? t('evaluationBuilder.runEvaluation.running')
                : t('evaluationBuilder.runEvaluation.run')}
            </Button>
          </div>
        </div>
      )}

      {/* Evaluation Control Modal */}
      <EvaluationControlModal
        isOpen={showEvaluationModal}
        projectId={projectId}
        evaluationConfigs={evaluations
          .filter((e) => e.enabled)
          .map((e) => ({
            id: e.id,
            metric: e.metric,
            prediction_fields: e.prediction_fields,
            reference_fields: e.reference_fields,
            metric_parameters: e.metric_parameters,
          }))}
        onClose={() => setShowEvaluationModal(false)}
        onSuccess={() => {
          setShowEvaluationModal(false)
          onSave?.()
        }}
      />
    </div>
  )
}
