/**
 * Aggregation Level Selector Component
 *
 * Multi-select dropdown for selecting units of observation for evaluation results:
 * - Per-sample: Individual prediction vs ground truth
 * - Per-model: Aggregate scores per model
 * - Per-field: Breakdown by evaluated field
 * - Overall: Single aggregate across everything
 */

'use client'

import {
  ChartBarIcon,
  CheckIcon,
  ChevronDownIcon,
  CircleStackIcon,
  CubeIcon,
  TableCellsIcon,
} from '@heroicons/react/24/outline'
import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'

export type AggregationLevel = 'sample' | 'model' | 'field' | 'overall'

interface AggregationOption {
  id: AggregationLevel
  label: string
  description: string
  icon: React.ComponentType<{ className?: string }>
}

function getAggregationOptions(t: (key: string) => string): AggregationOption[] {
  return [
    {
      id: 'sample',
      label: t('evaluation.aggregation.perSample'),
      description: t('evaluation.aggregation.perSampleDescription'),
      icon: TableCellsIcon,
    },
    {
      id: 'model',
      label: t('evaluation.aggregation.perModel'),
      description: t('evaluation.aggregation.perModelDescription'),
      icon: CubeIcon,
    },
    {
      id: 'field',
      label: t('evaluation.aggregation.perField'),
      description: t('evaluation.aggregation.perFieldDescription'),
      icon: CircleStackIcon,
    },
    {
      id: 'overall',
      label: t('evaluation.aggregation.overall'),
      description: t('evaluation.aggregation.overallDescription'),
      icon: ChartBarIcon,
    },
  ]
}

interface AggregationSelectorProps {
  levels: AggregationLevel[]
  onChange: (levels: AggregationLevel[]) => void
  availableLevels?: AggregationLevel[]
  className?: string
}

export function AggregationSelector({
  levels,
  onChange,
  availableLevels,
  className = '',
}: AggregationSelectorProps) {
  const { t } = useI18n()
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const AGGREGATION_OPTIONS = getAggregationOptions(t)

  const options = availableLevels
    ? AGGREGATION_OPTIONS.filter((opt) => availableLevels.includes(opt.id))
    : AGGREGATION_OPTIONS

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

  const toggleLevel = (level: AggregationLevel) => {
    if (levels.includes(level)) {
      // Don't allow deselecting all - keep at least one
      if (levels.length > 1) {
        onChange(levels.filter((l) => l !== level))
      }
    } else {
      onChange([...levels, level])
    }
  }

  const selectAll = () => {
    onChange(options.map((opt) => opt.id))
  }

  const getSelectedLabels = () => {
    if (levels.length === 0) return t('evaluation.aggregation.selectPlaceholder')
    if (levels.length === options.length) return t('evaluation.aggregation.allSelected')
    return levels
      .map((l) => AGGREGATION_OPTIONS.find((opt) => opt.id === l)?.label)
      .filter(Boolean)
      .join(', ')
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
        <div className="absolute z-50 mt-1 w-full rounded-lg border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-800">
          {/* Select all / Reset options */}
          <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2 dark:border-gray-700">
            <button
              type="button"
              onClick={selectAll}
              className="text-xs text-emerald-600 hover:text-emerald-700 dark:text-emerald-400 dark:hover:text-emerald-300"
            >
              {t('evaluation.aggregation.selectAll')}
            </button>
            <button
              type="button"
              onClick={() => onChange(['model'])}
              className="text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
            >
              {t('evaluation.aggregation.reset')}
            </button>
          </div>

          {/* Options */}
          <div className="max-h-60 overflow-auto py-1">
            {options.map((option) => {
              const Icon = option.icon
              const isSelected = levels.includes(option.id)

              return (
                <button
                  key={option.id}
                  type="button"
                  onClick={() => toggleLevel(option.id)}
                  className={`flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-gray-50 dark:hover:bg-gray-700 ${
                    isSelected ? 'bg-emerald-50 dark:bg-emerald-900/20' : ''
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
                    {isSelected && <CheckIcon className="h-3 w-3 text-white" />}
                  </div>

                  {/* Icon */}
                  <Icon
                    className={`h-5 w-5 shrink-0 ${
                      isSelected
                        ? 'text-emerald-600 dark:text-emerald-400'
                        : 'text-gray-400 dark:text-gray-500'
                    }`}
                  />

                  {/* Label and description */}
                  <div className="min-w-0 flex-1">
                    <div
                      className={`text-sm font-medium ${
                        isSelected
                          ? 'text-emerald-700 dark:text-emerald-300'
                          : 'text-gray-700 dark:text-gray-300'
                      }`}
                    >
                      {option.label}
                    </div>
                    <div className="truncate text-xs text-gray-500 dark:text-gray-400">
                      {option.description}
                    </div>
                  </div>
                </button>
              )
            })}
          </div>

          {/* Selected count */}
          <div className="border-t border-gray-100 px-3 py-2 text-xs text-gray-500 dark:border-gray-700 dark:text-gray-400">
            {t('evaluation.aggregation.selectedCount', { selected: levels.length, total: options.length })}
          </div>
        </div>
      )}
    </div>
  )
}
