/**
 * PredictionFieldsStep — wizard step 2 (prediction field selection).
 *
 * Extracted from EvaluationBuilder.tsx `renderWizardStep()`
 * (`case 'prediction_fields'`). Behavior-preserving extraction; rendered
 * output is identical.
 */

'use client'

import { Badge } from '@/components/shared/Badge'
import { Checkbox } from '@/components/shared/Checkbox'
import { useI18n } from '@/contexts/I18nContext'
import {
  getFieldDisplayName,
  HUMAN_FIELD_PREFIX,
  MODEL_FIELD_PREFIX,
  type AvailableEvaluationFields,
} from '@/lib/api/evaluation-types'

interface PredictionOption {
  value: string
  label: string
  type: 'special' | 'model' | 'human'
}

export interface PredictionFieldsStepProps {
  availableFields: AvailableEvaluationFields
  /** All prediction options (special + model + human), memoized by caller. */
  allPredictionOptions: PredictionOption[]
  /** Currently selected prediction fields. */
  selectedFields: string[]
  /** Toggles a prediction field (wizard's `handleFieldToggle`). */
  onFieldToggle: (
    fieldType: 'prediction_fields' | 'reference_fields',
    value: string
  ) => void
}

export function PredictionFieldsStep({
  availableFields,
  allPredictionOptions,
  selectedFields,
  onFieldToggle,
}: PredictionFieldsStepProps) {
  const { t } = useI18n()

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
                  checked={selectedFields.includes(
                    opt.value
                  )}
                  onChange={() =>
                    onFieldToggle('prediction_fields', opt.value)
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
                    checked={selectedFields.includes(
                      prefixed
                    )}
                    onChange={() =>
                      onFieldToggle('prediction_fields', prefixed)
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
                    checked={selectedFields.includes(
                      prefixed
                    )}
                    onChange={() =>
                      onFieldToggle('prediction_fields', prefixed)
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
}
