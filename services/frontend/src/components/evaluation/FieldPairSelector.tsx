/**
 * Field Pair Selector Component
 *
 * Allows users to filter evaluation results by specific
 * prediction → reference field pairs (units of observation).
 */

'use client'

import { useI18n } from '@/contexts/I18nContext'
import { getFieldLabel } from '@/lib/api/evaluation-types'
import {
  ArrowRightIcon,
  CheckIcon,
  ChevronDownIcon,
} from '@heroicons/react/24/outline'
import { useEffect, useRef, useState } from 'react'

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
    if (selectedPairs.length === 0)
      return t('evaluation.fieldPair.selectPlaceholder')
    if (selectedPairs.length === fieldPairs.length)
      return t('evaluation.fieldPair.allPairs')
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
      <label className="mb-1 block text-xs font-medium text-zinc-500 dark:text-zinc-400">
        {t('evaluation.fieldPair.label')}
      </label>

      <button
        type="button"
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        className={`flex w-full items-center justify-between rounded-full bg-white px-4 py-2 text-sm ring-1 ring-zinc-900/10 transition focus:ring-2 focus:ring-emerald-500 focus:outline-none dark:bg-white/5 dark:ring-white/10 dark:ring-inset ${
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
        <div className="absolute z-50 mt-1 w-72 rounded-lg border border-zinc-200 bg-white shadow-lg dark:border-zinc-700 dark:bg-zinc-800">
          {/* Quick actions */}
          <div className="flex items-center justify-between border-b border-zinc-100 px-3 py-2 dark:border-zinc-700">
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
              className="text-xs text-zinc-500 hover:text-zinc-700 dark:text-zinc-400"
            >
              {t('evaluation.fieldPair.clear')}
            </button>
          </div>

          <div className="max-h-60 overflow-auto py-1">
            {/* Model response pairs */}
            {modelPairs.length > 0 && (
              <div>
                <div className="bg-zinc-50 px-3 py-1.5 text-xs font-semibold text-zinc-500 dark:bg-zinc-900/50 dark:text-zinc-400">
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
                <div className="bg-zinc-50 px-3 py-1.5 text-xs font-semibold text-zinc-500 dark:bg-zinc-900/50 dark:text-zinc-400">
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
          <div className="border-t border-zinc-100 px-3 py-2 text-xs text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
            {t('evaluation.fieldPair.selectedCount', {
              selected: selectedPairs.length,
              total: fieldPairs.length,
            })}
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
      className={`flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-zinc-50 dark:hover:bg-zinc-700 ${isSelected ? 'bg-emerald-50 dark:bg-emerald-900/20' : ''} ${pair.hasResults === false ? 'opacity-50' : ''} `}
    >
      {/* Checkbox indicator */}
      <div
        className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
          isSelected
            ? 'border-emerald-500 bg-emerald-500'
            : 'border-zinc-300 dark:border-zinc-600'
        } `}
      >
        {isSelected && <CheckIcon className="h-3 w-3 text-white" />}
      </div>

      {/* Field pair display */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1 text-sm">
          <span
            className={`truncate font-medium ${isSelected ? 'text-emerald-700 dark:text-emerald-300' : 'text-zinc-700 dark:text-zinc-300'}`}
          >
            {getFieldLabel(pair.predictionField, t)}
          </span>
          <ArrowRightIcon className="h-3 w-3 shrink-0 text-zinc-400" />
          <span
            className={`truncate ${isSelected ? 'text-emerald-600 dark:text-emerald-400' : 'text-zinc-600 dark:text-zinc-400'}`}
          >
            {pair.referenceField}
          </span>
        </div>
        {pair.resultCount !== undefined && (
          <div className="text-xs text-zinc-400">
            {t('evaluation.fieldPair.resultCount', { count: pair.resultCount })}
          </div>
        )}
      </div>

      {/* No results indicator */}
      {pair.hasResults === false && (
        <span className="text-xs whitespace-nowrap text-amber-500 dark:text-amber-400">
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
  resultsMap?: Record<string, { hasResults: boolean; resultCount: number }>,
): FieldPair[] {
  const pairs: FieldPair[] = []
  const seenPairs = new Set<string>()

  evaluationConfigs.forEach((config) => {
    config.prediction_fields.forEach((predField) => {
      config.reference_fields.forEach((refField) => {
        const pairKey = `${predField}→${refField}`
        if (!seenPairs.has(pairKey)) {
          seenPairs.add(pairKey)

          // Determine source based on prefix convention
          const isHuman =
            predField.startsWith('human:') || predField === '__all_human__'
          const source: 'model' | 'human' = isHuman ? 'human' : 'model'

          const resultInfo = resultsMap?.[pairKey]

          pairs.push({
            id: pairKey,
            predictionField: predField,
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
