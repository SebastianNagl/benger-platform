/**
 * Metric Selector Component
 *
 * Multi-select component for selecting evaluation metrics with:
 * - Grouped metrics by category
 * - Collapsible category sections
 * - Search filter
 * - Preset selections
 */

'use client'

import { Badge } from '@/components/shared/Badge'
import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { Checkbox } from '@/components/shared/Checkbox'
import { useI18n } from '@/contexts/I18nContext'
import {
  ChevronDownIcon,
  ChevronRightIcon,
  MagnifyingGlassIcon,
} from '@heroicons/react/24/outline'
import { useState } from 'react'

interface MetricSelectorProps {
  availableMetrics: string[]
  selectedMetrics: string[]
  onSelectionChange: (metrics: string[]) => void
  groupByCategory?: boolean
}

const METRIC_CATEGORIES = [
  {
    name: 'Lexical Metrics',
    description: 'String and surface-level matching',
    metrics: [
      'exact_match',
      'edit_distance',
      'bleu',
      'rouge',
      'meteor',
      'chrf',
    ],
  },
  {
    name: 'Classification Metrics',
    description: 'For categorical predictions',
    metrics: [
      'accuracy',
      'precision',
      'recall',
      'f1',
      'cohen_kappa',
      'confusion_matrix',
    ],
  },
  {
    name: 'Multi-label/Set Metrics',
    description: 'For multi-label or set predictions',
    metrics: ['jaccard', 'hamming_loss', 'subset_accuracy', 'token_f1'],
  },
  {
    name: 'Regression Metrics',
    description: 'For numeric predictions',
    metrics: ['mae', 'rmse', 'mape', 'r2', 'correlation'],
  },
  {
    name: 'Ranking Metrics',
    description: 'For ranked results evaluation',
    metrics: [
      'ndcg',
      'map',
      'spearman_correlation',
      'kendall_tau',
      'weighted_kappa',
    ],
  },
  {
    name: 'Semantic Similarity',
    description: 'Embedding-based semantic comparison',
    metrics: ['semantic_similarity', 'bertscore', 'moverscore'],
  },
  {
    name: 'Factuality & Coherence',
    description: 'Content quality evaluation',
    metrics: ['factcc', 'qags', 'coherence'],
  },
  {
    name: 'Structured Data',
    description: 'JSON and schema validation',
    metrics: ['json_accuracy', 'schema_validation', 'field_accuracy'],
  },
  {
    name: 'Span/Sequence Labeling',
    description: 'For token or span-level predictions',
    metrics: ['span_exact_match', 'iou', 'partial_match', 'boundary_accuracy'],
  },
  {
    name: 'Hierarchical Metrics',
    description: 'For hierarchical classifications',
    metrics: ['hierarchical_f1', 'path_accuracy', 'lca_accuracy'],
  },
  {
    name: 'LLM-as-Judge',
    description: 'AI model-based evaluation (requires API key)',
    metrics: [
      'llm_judge_classic',
      'llm_judge_custom',
    ],
  },
]

const PRESET_SELECTIONS = {
  'Standard NLG Metrics': ['bleu', 'rouge', 'meteor', 'bertscore'],
  'Classification Suite': ['accuracy', 'precision', 'recall', 'f1'],
  'Semantic Suite': ['semantic_similarity', 'bertscore', 'moverscore'],
  'All Available': [] as string[], // Will be filled with all available metrics
}

export function MetricSelector({
  availableMetrics,
  selectedMetrics,
  onSelectionChange,
  groupByCategory = true,
}: MetricSelectorProps) {
  const { t } = useI18n()
  const [searchQuery, setSearchQuery] = useState('')
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(
    new Set()
  )

  const toggleCategory = (categoryName: string) => {
    setExpandedCategories((prev) => {
      const next = new Set(prev)
      if (next.has(categoryName)) {
        next.delete(categoryName)
      } else {
        next.add(categoryName)
      }
      return next
    })
  }

  const toggleMetric = (metric: string) => {
    const isSelected = selectedMetrics.includes(metric)
    if (isSelected) {
      onSelectionChange(selectedMetrics.filter((m) => m !== metric))
    } else {
      onSelectionChange([...selectedMetrics, metric])
    }
  }

  const applyPreset = (presetName: string) => {
    let metricsToSelect =
      PRESET_SELECTIONS[presetName as keyof typeof PRESET_SELECTIONS]

    if (presetName === 'All Available') {
      metricsToSelect = availableMetrics
    } else {
      metricsToSelect = metricsToSelect.filter((m) =>
        availableMetrics.includes(m)
      )
    }

    onSelectionChange(metricsToSelect)
  }

  const clearSelection = () => {
    onSelectionChange([])
  }

  const filteredCategories = METRIC_CATEGORIES.map((category) => {
    const filteredMetrics = category.metrics.filter(
      (metric) =>
        availableMetrics.includes(metric) &&
        (searchQuery === '' ||
          metric.toLowerCase().includes(searchQuery.toLowerCase()))
    )
    return { ...category, metrics: filteredMetrics }
  }).filter((category) => category.metrics.length > 0)

  const allFilteredMetrics = filteredCategories.flatMap(
    (category) => category.metrics
  )

  return (
    <Card className="p-4">
      <div className="space-y-4">
        {/* Header with selection count */}
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              {t('evaluation.metricSelector.selectMetrics')}
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {t('evaluation.metricSelector.selectedCount', { selected: selectedMetrics.length, total: availableMetrics.length })}
            </p>
          </div>
          <Button variant="text" onClick={clearSelection}>
            {t('evaluation.metricSelector.clearAll')}
          </Button>
        </div>

        {/* Search Input */}
        <div className="relative">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder={t('evaluation.metricSelector.searchPlaceholder')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-md border border-gray-300 bg-white py-2 pl-10 pr-4 text-sm text-gray-900 placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
          />
        </div>

        {/* Preset Selections */}
        <div>
          <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
            {t('evaluation.metricSelector.quickPresets')}
          </label>
          <div className="flex flex-wrap gap-2">
            {Object.keys(PRESET_SELECTIONS).map((presetName) => (
              <Button
                key={presetName}
                variant="secondary"
                onClick={() => applyPreset(presetName)}
                className="text-xs"
              >
                {presetName}
              </Button>
            ))}
          </div>
        </div>

        {/* Metric Categories */}
        {groupByCategory ? (
          <div className="space-y-2">
            {filteredCategories.map((category) => {
              const isExpanded = expandedCategories.has(category.name)
              const selectedInCategory = category.metrics.filter((m) =>
                selectedMetrics.includes(m)
              ).length

              return (
                <div
                  key={category.name}
                  className="rounded-lg border border-gray-200 dark:border-gray-700"
                >
                  {/* Category Header */}
                  <div
                    className="dark:hover:bg-gray-750 flex cursor-pointer items-center justify-between bg-gray-50 px-4 py-3 hover:bg-gray-100 dark:bg-gray-800"
                    onClick={() => toggleCategory(category.name)}
                  >
                    <div className="flex items-center space-x-2">
                      {isExpanded ? (
                        <ChevronDownIcon className="h-4 w-4 text-gray-500" />
                      ) : (
                        <ChevronRightIcon className="h-4 w-4 text-gray-500" />
                      )}
                      <div>
                        <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100">
                          {category.name}
                        </h4>
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                          {category.description}
                        </p>
                      </div>
                    </div>
                    <Badge variant="secondary" className="text-xs">
                      {selectedInCategory}/{category.metrics.length}
                    </Badge>
                  </div>

                  {/* Category Metrics */}
                  {isExpanded && (
                    <div className="space-y-1 p-4">
                      {category.metrics.map((metric) => {
                        const isSelected = selectedMetrics.includes(metric)
                        return (
                          <label
                            key={metric}
                            className="flex cursor-pointer items-center space-x-2 rounded p-2 hover:bg-gray-50 dark:hover:bg-gray-800"
                          >
                            <Checkbox
                              checked={isSelected}
                              onChange={() => toggleMetric(metric)}
                            />
                            <span className="flex-1 text-sm font-medium text-gray-700 dark:text-gray-300">
                              {metric}
                            </span>
                          </label>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        ) : (
          /* Flat List View */
          <div className="space-y-1">
            {allFilteredMetrics.map((metric) => {
              const isSelected = selectedMetrics.includes(metric)
              return (
                <label
                  key={metric}
                  className="flex cursor-pointer items-center space-x-2 rounded p-2 hover:bg-gray-50 dark:hover:bg-gray-800"
                >
                  <Checkbox
                    checked={isSelected}
                    onChange={() => toggleMetric(metric)}
                  />
                  <span className="flex-1 text-sm font-medium text-gray-700 dark:text-gray-300">
                    {metric}
                  </span>
                </label>
              )
            })}
          </div>
        )}

        {/* No Results Message */}
        {allFilteredMetrics.length === 0 && (
          <div className="py-8 text-center text-sm text-gray-500 dark:text-gray-400">
            {t('evaluation.metricSelector.noResults')}
          </div>
        )}
      </div>
    </Card>
  )
}
