/**
 * ReferenceFieldsStep — wizard step 3 (reference field selection).
 *
 * Extracted from EvaluationBuilder.tsx `renderWizardStep()`
 * (`case 'reference_fields'`). Behavior-preserving extraction; rendered
 * output is identical.
 */

'use client'

import { Badge } from '@/components/shared/Badge'
import { Checkbox } from '@/components/shared/Checkbox'
import { useI18n } from '@/contexts/I18nContext'
import { InformationCircleIcon } from '@heroicons/react/24/outline'

interface ReferenceOption {
  value: string
  label: string
}

export interface ReferenceFieldsStepProps {
  /** Reference field options, memoized by caller. */
  referenceOptions: ReferenceOption[]
  /** Currently selected reference fields. */
  selectedFields: string[]
  /** Toggles a reference field (wizard's `handleFieldToggle`). */
  onFieldToggle: (
    fieldType: 'prediction_fields' | 'reference_fields',
    value: string
  ) => void
}

export function ReferenceFieldsStep({
  referenceOptions,
  selectedFields,
  onFieldToggle,
}: ReferenceFieldsStepProps) {
  const { t } = useI18n()

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
                checked={selectedFields.includes(
                  opt.value
                )}
                onChange={() =>
                  onFieldToggle('reference_fields', opt.value)
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
      {selectedFields.length > 1 && (
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
}
