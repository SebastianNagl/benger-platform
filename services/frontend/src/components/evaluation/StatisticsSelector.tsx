/**
 * Statistical Methods Selector Component (Dropdown Version)
 *
 * Compact dropdown for selecting statistical analyses:
 * - Confidence Intervals (95% CI)
 * - T-tests (paired/independent)
 * - Bootstrap significance (10k resamples)
 * - Cohen's d (effect size)
 * - Cliff's delta (non-parametric effect size)
 * - Correlation (Pearson/Spearman between metrics)
 */

'use client'

import {
  ArrowTrendingUpIcon,
  BeakerIcon,
  CheckIcon,
  ChevronDownIcon,
  ScaleIcon,
} from '@heroicons/react/24/outline'
import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'

export type StatisticalMethod =
  | 'ci'
  | 'se'
  | 'std'
  | 'ttest'
  | 'bootstrap'
  | 'cohens_d'
  | 'cliffs_delta'
  | 'correlation'

interface StatMethod {
  id: StatisticalMethod
  label: string
  shortLabel: string
  category: 'basic' | 'significance' | 'effect_size' | 'relationship'
}

function getStatisticalMethods(t: (key: string) => string): StatMethod[] {
  return [
    {
      id: 'ci',
      label: t('evaluation.statistics.ci'),
      shortLabel: t('evaluation.statistics.ciShort'),
      category: 'basic',
    },
    {
      id: 'se',
      label: t('evaluation.statistics.se'),
      shortLabel: t('evaluation.statistics.seShort'),
      category: 'basic',
    },
    {
      id: 'std',
      label: t('evaluation.statistics.std'),
      shortLabel: t('evaluation.statistics.stdShort'),
      category: 'basic',
    },
    {
      id: 'ttest',
      label: t('evaluation.statistics.ttest'),
      shortLabel: t('evaluation.statistics.ttestShort'),
      category: 'significance',
    },
    {
      id: 'bootstrap',
      label: t('evaluation.statistics.bootstrap'),
      shortLabel: t('evaluation.statistics.bootstrapShort'),
      category: 'significance',
    },
    {
      id: 'cohens_d',
      label: t('evaluation.statistics.cohensD'),
      shortLabel: t('evaluation.statistics.cohensDShort'),
      category: 'effect_size',
    },
    {
      id: 'cliffs_delta',
      label: t('evaluation.statistics.cliffsDelta'),
      shortLabel: t('evaluation.statistics.cliffsDeltaShort'),
      category: 'effect_size',
    },
    {
      id: 'correlation',
      label: t('evaluation.statistics.correlation'),
      shortLabel: t('evaluation.statistics.correlationShort'),
      category: 'relationship',
    },
  ]
}

function getCategories(t: (key: string) => string) {
  return [
    { id: 'basic', label: t('evaluation.statistics.categoryBasic'), icon: ArrowTrendingUpIcon },
    { id: 'significance', label: t('evaluation.statistics.categorySignificance'), icon: BeakerIcon },
    { id: 'effect_size', label: t('evaluation.statistics.categoryEffectSize'), icon: ScaleIcon },
    { id: 'relationship', label: t('evaluation.statistics.categoryRelationship'), icon: ArrowTrendingUpIcon },
  ]
}

interface StatisticsSelectorProps {
  selectedMethods: StatisticalMethod[]
  onChange: (methods: StatisticalMethod[]) => void
  className?: string
}

export function StatisticsSelector({
  selectedMethods,
  onChange,
  className = '',
}: StatisticsSelectorProps) {
  const { t } = useI18n()
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const STATISTICAL_METHODS = getStatisticalMethods(t)
  const CATEGORIES = getCategories(t)

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const toggleMethod = (method: StatisticalMethod) => {
    if (selectedMethods.includes(method)) {
      onChange(selectedMethods.filter((m) => m !== method))
    } else {
      onChange([...selectedMethods, method])
    }
  }

  const selectAll = () => {
    onChange(STATISTICAL_METHODS.map((m) => m.id))
  }

  const getSelectedLabels = () => {
    if (selectedMethods.length === 0) return t('evaluation.statistics.selectPlaceholder')
    if (selectedMethods.length === STATISTICAL_METHODS.length)
      return t('evaluation.statistics.allMethods')
    if (selectedMethods.length <= 2) {
      return selectedMethods
        .map((m) => STATISTICAL_METHODS.find((s) => s.id === m)?.shortLabel)
        .filter(Boolean)
        .join(', ')
    }
    return t('evaluation.statistics.nSelected', { n: selectedMethods.length })
  }

  return (
    <div className={`relative ${className}`} ref={dropdownRef}>
      {/* Dropdown trigger */}
      <Button
        variant="outline"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full justify-between text-left"
      >
        <span className="truncate">
          {getSelectedLabels()}
        </span>
        <ChevronDownIcon
          className={`h-4 w-4 opacity-70 transition-transform ${isOpen ? 'rotate-180' : ''}`}
        />
      </Button>

      {/* Dropdown menu */}
      {isOpen && (
        <div className="absolute z-50 mt-1 w-64 rounded-lg border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-800">
          {/* Select all / Clear all options */}
          <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2 dark:border-gray-700">
            <button
              type="button"
              onClick={selectAll}
              className="text-xs text-emerald-600 hover:text-emerald-700 dark:text-emerald-400 dark:hover:text-emerald-300"
            >
              {t('evaluation.statistics.selectAll')}
            </button>
            <button
              type="button"
              onClick={() => onChange([])}
              className="text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
            >
              {t('evaluation.statistics.clearAll')}
            </button>
          </div>

          {/* Options grouped by category */}
          <div className="max-h-60 overflow-auto py-1">
            {CATEGORIES.map((category) => {
              const Icon = category.icon
              const methods = STATISTICAL_METHODS.filter(
                (m) => m.category === category.id
              )

              return (
                <div key={category.id}>
                  {/* Category header */}
                  <div className="flex items-center gap-2 bg-gray-50 px-3 py-1.5 dark:bg-gray-900/50">
                    <Icon className="h-3.5 w-3.5 text-gray-400" />
                    <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                      {category.label}
                    </span>
                  </div>

                  {/* Methods in this category */}
                  {methods.map((method) => {
                    const isSelected = selectedMethods.includes(method.id)

                    return (
                      <button
                        key={method.id}
                        type="button"
                        onClick={() => toggleMethod(method.id)}
                        className={`flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-gray-50 dark:hover:bg-gray-700 ${
                          isSelected
                            ? 'bg-emerald-50 dark:bg-emerald-900/20'
                            : ''
                        }`}
                      >
                        {/* Checkbox indicator */}
                        <div
                          className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                            isSelected
                              ? 'border-emerald-500 bg-emerald-500'
                              : 'border-gray-300 dark:border-gray-600'
                          }`}
                        >
                          {isSelected && (
                            <CheckIcon className="h-3 w-3 text-white" />
                          )}
                        </div>

                        {/* Label */}
                        <span
                          className={`text-sm ${
                            isSelected
                              ? 'font-medium text-emerald-700 dark:text-emerald-300'
                              : 'text-gray-700 dark:text-gray-300'
                          }`}
                        >
                          {method.label}
                        </span>
                      </button>
                    )
                  })}
                </div>
              )
            })}
          </div>

          {/* Selected count */}
          <div className="border-t border-gray-100 px-3 py-2 text-xs text-gray-500 dark:border-gray-700 dark:text-gray-400">
            {t('evaluation.statistics.selectedCount', { selected: selectedMethods.length, total: STATISTICAL_METHODS.length })}
          </div>
        </div>
      )}
    </div>
  )
}
