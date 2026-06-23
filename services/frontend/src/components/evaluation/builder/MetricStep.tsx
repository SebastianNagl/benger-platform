/**
 * MetricStep — wizard step 1 (metric selection).
 *
 * Extracted from EvaluationBuilder.tsx `renderWizardStep()` (`case 'metric'`).
 * Behavior-preserving extraction; rendered output is identical.
 */

'use client'

import { useI18n } from '@/contexts/I18nContext'
import {
  getGroupedMetrics,
  getMetricDefinitions,
} from '@/lib/api/evaluation-types'

export interface MetricStepProps {
  /** Currently selected metric id (from `newEvaluation.metric`). */
  selectedMetric: string
  /** Selects a metric (wizard's `handleMetricSelect`). */
  onSelectMetric: (metric: string) => void
}

export function MetricStep({ selectedMetric, onSelectMetric }: MetricStepProps) {
  const { t } = useI18n()

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
                const isSelected = selectedMetric === metric

                return (
                  <button
                    key={metric}
                    onClick={() => onSelectMetric(metric)}
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
}
