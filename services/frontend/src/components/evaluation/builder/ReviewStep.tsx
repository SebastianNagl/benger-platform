/**
 * ReviewStep — wizard final step (review summary).
 *
 * Extracted from EvaluationBuilder.tsx `renderWizardStep()` (`case 'review'`).
 * Behavior-preserving extraction; rendered output is identical.
 */

'use client'

import { Badge } from '@/components/shared/Badge'
import { useI18n } from '@/contexts/I18nContext'
import {
  getFieldDisplayName,
  getMetricDefinitions,
} from '@/lib/api/evaluation-types'

export interface ReviewStepProps {
  metric: string
  predictionFields: string[]
  referenceFields: string[]
  metricParameters: Record<string, any>
}

export function ReviewStep({
  metric,
  predictionFields,
  referenceFields,
  metricParameters,
}: ReviewStepProps) {
  const { t } = useI18n()
  const reviewMetricDef = getMetricDefinitions()[metric]

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
            {reviewMetricDef?.display_name || metric}
          </p>
        </div>
        <div>
          <span className="text-xs text-gray-500">
            {t('evaluationBuilder.review.predictionFields')}:
          </span>
          <div className="mt-1 flex flex-wrap gap-1">
            {predictionFields.map((field) => (
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
            {referenceFields.map((field) => (
              <Badge key={field} variant="default" className="text-xs">
                {field}
              </Badge>
            ))}
          </div>
        </div>
        {Object.keys(metricParameters).length > 0 && (
          <div>
            <span className="text-xs text-gray-500">
              {t('evaluationBuilder.review.parameters')}:
            </span>
            <pre className="mt-1 overflow-x-auto rounded bg-gray-100 p-2 text-xs dark:bg-gray-700">
              {JSON.stringify(metricParameters, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  )
}
