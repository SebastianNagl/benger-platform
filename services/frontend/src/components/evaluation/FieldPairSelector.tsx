/**
 * Field Pair Selector Component
 *
 * Allows users to filter evaluation results by specific
 * prediction → reference field pairs (units of observation).
 */

'use client'

import {
  ArrowRightIcon,
  CheckIcon,
  ChevronDownIcon,
} from '@heroicons/react/24/outline'
import { useEffect, useRef, useState } from 'react'
import { useI18n } from '@/contexts/I18nContext'

export interface FieldPair {
  id: string
  predictionField: string
  referenceField: string
  displayLabel: string
  source: 'model' | 'human'
  hasResults?: boolean
  resultCount?: number
}

interface FieldPairSelectorProps {
  fieldPairs: FieldPair[]
  selectedPairs: string[]
  onChange: (selectedIds: string[]) => void
  className?: string
  disabled?: boolean
}

export function FieldPairSelector({
  fieldPairs,
  selectedPairs,
  onChange,
  className = '',
  disabled = false,
}: FieldPairSelectorProps) {
  const { t } = useI18n()
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

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

  const togglePair = (pairId: string) => {
    if (selectedPairs.includes(pairId)) {
      // Don't allow deselecting all
      if (selectedPairs.length > 1) {
        onChange(selectedPairs.filter((id) => id !== pairId))
      }
    } else {
      onChange([...selectedPairs, pairId])
    }
  }

  const selectAll = () => {
    onChange(fieldPairs.map((fp) => fp.id))
  }

  const clearAll = () => {
    // Keep at least one selected
    if (fieldPairs.length > 0) {
      onChange([fieldPairs[0].id])
    }
  }

  const getDisplayText = () => {
    if (selectedPairs.length === 0) return t('evaluation.fieldPair.selectPlaceholder')
    if (selectedPairs.length === fieldPairs.length) return t('evaluation.fieldPair.allPairs')
    if (selectedPairs.length === 1) {
      const pair = fieldPairs.find((fp) => fp.id === selectedPairs[0])
      return pair?.displayLabel || t('evaluation.fieldPair.nSelected', { n: 1 })
    }
    return t('evaluation.fieldPair.nSelected', { n: selectedPairs.length })
  }

  // Group field pairs by source (model vs human)
  const modelPairs = fieldPairs.filter((fp) => fp.source === 'model')
  const humanPairs = fieldPairs.filter((fp) => fp.source === 'human')

  if (fieldPairs.length === 0) {
    return null
  }

  return (
    <div className={`relative ${className}`} ref={dropdownRef}>
      <label className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">
        {t('evaluation.fieldPair.label')}
      </label>

      <button
        type="button"
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        className={`flex w-full items-center justify-between rounded-full bg-white px-4 py-2 text-sm ring-1 ring-zinc-900/10 transition focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:bg-white/5 dark:ring-inset dark:ring-white/10 ${
          disabled
            ? 'cursor-not-allowed opacity-50'
            : 'hover:ring-zinc-900/20 dark:hover:ring-white/20'
        } `}
      >
        <span className="truncate text-zinc-900 dark:text-white">
          {getDisplayText()}
        </span>
        <ChevronDownIcon
          className={`h-4 w-4 opacity-70 transition-transform ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>

      {isOpen && (
        <div className="absolute z-50 mt-1 w-72 rounded-lg border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-800">
          {/* Quick actions */}
          <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2 dark:border-gray-700">
            <button
              type="button"
              onClick={selectAll}
              className="text-xs text-emerald-600 hover:text-emerald-700 dark:text-emerald-400"
            >
              {t('evaluation.fieldPair.selectAll')}
            </button>
            <button
              type="button"
              onClick={clearAll}
              className="text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400"
            >
              {t('evaluation.fieldPair.clear')}
            </button>
          </div>

          <div className="max-h-60 overflow-auto py-1">
            {/* Model response pairs */}
            {modelPairs.length > 0 && (
              <div>
                <div className="bg-gray-50 px-3 py-1.5 text-xs font-semibold text-gray-500 dark:bg-gray-900/50 dark:text-gray-400">
                  {t('evaluation.fieldPair.modelResponses')}
                </div>
                {modelPairs.map((pair) => (
                  <FieldPairOption
                    key={pair.id}
                    pair={pair}
                    isSelected={selectedPairs.includes(pair.id)}
                    onToggle={() => togglePair(pair.id)}
                  />
                ))}
              </div>
            )}

            {/* Human annotation pairs */}
            {humanPairs.length > 0 && (
              <div>
                <div className="bg-gray-50 px-3 py-1.5 text-xs font-semibold text-gray-500 dark:bg-gray-900/50 dark:text-gray-400">
                  {t('evaluation.fieldPair.humanAnnotations')}
                </div>
                {humanPairs.map((pair) => (
                  <FieldPairOption
                    key={pair.id}
                    pair={pair}
                    isSelected={selectedPairs.includes(pair.id)}
                    onToggle={() => togglePair(pair.id)}
                  />
                ))}
              </div>
            )}

            {/* If no grouping needed */}
            {modelPairs.length === 0 &&
              humanPairs.length === 0 &&
              fieldPairs.map((pair) => (
                <FieldPairOption
                  key={pair.id}
                  pair={pair}
                  isSelected={selectedPairs.includes(pair.id)}
                  onToggle={() => togglePair(pair.id)}
                />
              ))}
          </div>

          {/* Selected count */}
          <div className="border-t border-gray-100 px-3 py-2 text-xs text-gray-500 dark:border-gray-700 dark:text-gray-400">
            {t('evaluation.fieldPair.selectedCount', { selected: selectedPairs.length, total: fieldPairs.length })}
          </div>
        </div>
      )}
    </div>
  )
}

interface FieldPairOptionProps {
  pair: FieldPair
  isSelected: boolean
  onToggle: () => void
}

function FieldPairOption({ pair, isSelected, onToggle }: FieldPairOptionProps) {
  const { t } = useI18n()
  return (
    <button
      type="button"
      onClick={onToggle}
      className={`flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-gray-50 dark:hover:bg-gray-700 ${isSelected ? 'bg-emerald-50 dark:bg-emerald-900/20' : ''} ${pair.hasResults === false ? 'opacity-50' : ''} `}
    >
      {/* Checkbox indicator */}
      <div
        className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
          isSelected
            ? 'border-emerald-500 bg-emerald-500'
            : 'border-gray-300 dark:border-gray-600'
        } `}
      >
        {isSelected && <CheckIcon className="h-3 w-3 text-white" />}
      </div>

      {/* Field pair display */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1 text-sm">
          <span
            className={`truncate font-medium ${isSelected ? 'text-emerald-700 dark:text-emerald-300' : 'text-gray-700 dark:text-gray-300'}`}
          >
            {pair.predictionField}
          </span>
          <ArrowRightIcon className="h-3 w-3 shrink-0 text-gray-400" />
          <span
            className={`truncate ${isSelected ? 'text-emerald-600 dark:text-emerald-400' : 'text-gray-600 dark:text-gray-400'}`}
          >
            {pair.referenceField}
          </span>
        </div>
        {pair.resultCount !== undefined && (
          <div className="text-xs text-gray-400">
            {t('evaluation.fieldPair.resultCount', { count: pair.resultCount })}
          </div>
        )}
      </div>

      {/* No results indicator */}
      {pair.hasResults === false && (
        <span className="whitespace-nowrap text-xs text-amber-500 dark:text-amber-400">
          {t('evaluation.fieldPair.noResults')}
        </span>
      )}
    </button>
  )
}

/**
 * Helper function to extract field pairs from evaluation configs
 */
export function extractFieldPairsFromConfig(
  evaluationConfigs: Array<{
    id: string
    prediction_fields: string[]
    reference_fields: string[]
    metric?: string
  }>,
  resultsMap?: Record<string, { hasResults: boolean; resultCount: number }>
): FieldPair[] {
  const pairs: FieldPair[] = []
  const seenPairs = new Set<string>()

  evaluationConfigs.forEach((config) => {
    config.prediction_fields.forEach((predField) => {
      config.reference_fields.forEach((refField) => {
        const pairKey = `${predField}→${refField}`
        if (!seenPairs.has(pairKey)) {
          seenPairs.add(pairKey)

          // Determine source based on field name patterns
          const isModelField =
            predField.startsWith('generation_') ||
            predField.includes('model') ||
            predField === '__all_model__'
          const source: 'model' | 'human' = isModelField ? 'model' : 'human'

          const resultInfo = resultsMap?.[pairKey]

          pairs.push({
            id: pairKey,
            predictionField: predField
              .replace('__all_model__', 'All Models')
              .replace('__all_human__', 'All Human'),
            referenceField: refField,
            displayLabel: `${predField} → ${refField}`,
            source,
            hasResults: resultInfo?.hasResults,
            resultCount: resultInfo?.resultCount,
          })
        }
      })
    })
  })

  return pairs
}
