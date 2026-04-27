/**
 * Chart Type Selector Component
 *
 * Dropdown for selecting between different chart visualization types.
 * Includes a 'data' view that shows only the data table without charts.
 */

'use client'

import { useHydration } from '@/contexts/HydrationContext'
import { useI18n } from '@/contexts/I18nContext'
import {
  ChartBarIcon,
  ChartPieIcon,
  ChevronDownIcon,
  Square3Stack3DIcon,
  Squares2X2Icon,
  TableCellsIcon,
} from '@heroicons/react/24/outline'
import { useEffect, useMemo, useRef, useState } from 'react'

export type ChartType = 'data' | 'bar' | 'radar' | 'box' | 'heatmap' | 'table'

interface ChartTypeConfig {
  type: ChartType
  label: string
  description: string
  icon: React.ComponentType<{ className?: string }>
  bestFor: string
  requiresMultipleModels?: boolean
  requiresDistributionData?: boolean
}

function getChartTypes(t: (key: string) => string): ChartTypeConfig[] {
  return [
    {
      type: 'data',
      label: t('evaluation.chartType.dataView'),
      description: t('evaluation.chartType.dataViewDescription'),
      icon: TableCellsIcon,
      bestFor: t('evaluation.chartType.dataViewBestFor'),
    },
    {
      type: 'bar',
      label: t('evaluation.chartType.barChart'),
      description: t('evaluation.chartType.barChartDescription'),
      icon: ChartBarIcon,
      bestFor: t('evaluation.chartType.barChartBestFor'),
    },
    {
      type: 'radar',
      label: t('evaluation.chartType.radarChart'),
      description: t('evaluation.chartType.radarChartDescription'),
      icon: ChartPieIcon,
      bestFor: t('evaluation.chartType.radarChartBestFor'),
      requiresMultipleModels: false,
    },
    {
      type: 'box',
      label: t('evaluation.chartType.boxPlot'),
      description: t('evaluation.chartType.boxPlotDescription'),
      icon: Square3Stack3DIcon,
      bestFor: t('evaluation.chartType.boxPlotBestFor'),
      requiresDistributionData: true,
    },
    {
      type: 'heatmap',
      label: t('evaluation.chartType.heatmap'),
      description: t('evaluation.chartType.heatmapDescription'),
      icon: Squares2X2Icon,
      bestFor: t('evaluation.chartType.heatmapBestFor'),
      requiresMultipleModels: true,
    },
    {
      type: 'table',
      label: t('evaluation.chartType.tableChart'),
      description: t('evaluation.chartType.tableChartDescription'),
      icon: Squares2X2Icon,
      bestFor: t('evaluation.chartType.tableChartBestFor'),
    },
  ]
}

interface ChartTypeSelectorProps {
  selectedType: ChartType
  onChange: (type: ChartType) => void
  availableTypes?: ChartType[]
  disabledTypes?: ChartType[]
  disabledReasons?: Partial<Record<ChartType, string>>
  className?: string
  size?: 'sm' | 'md'
}

const STORAGE_KEY = 'benger-preferred-chart-type'

export function ChartTypeSelector({
  selectedType,
  onChange,
  availableTypes,
  disabledTypes = [],
  disabledReasons = {},
  className = '',
  size = 'md',
}: ChartTypeSelectorProps) {
  const { t } = useI18n()
  const mounted = useHydration()
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const hasLoadedPreference = useRef(false)

  const CHART_TYPES = useMemo(() => getChartTypes(t), [t])

  // Load preference from localStorage after hydration
  // Only apply if current selection is the default (no URL override)
  useEffect(() => {
    if (!mounted || hasLoadedPreference.current) return
    hasLoadedPreference.current = true

    // Don't override if URL already set a non-default chart type
    if (selectedType !== 'data') return

    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved && CHART_TYPES.some((ct) => ct.type === saved)) {
      const savedType = saved as ChartType
      if (
        !disabledTypes.includes(savedType) &&
        (!availableTypes || availableTypes.includes(savedType))
      ) {
        onChange(savedType)
      }
    }
  }, [mounted, availableTypes, disabledTypes, onChange, selectedType])

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

  // Save preference when changed
  const handleSelect = (type: ChartType) => {
    onChange(type)
    setIsOpen(false)
    if (mounted) {
      localStorage.setItem(STORAGE_KEY, type)
    }
  }

  const filteredTypes = availableTypes
    ? CHART_TYPES.filter((ct) => availableTypes.includes(ct.type))
    : CHART_TYPES

  const selectedConfig = CHART_TYPES.find((ct) => ct.type === selectedType)

  const buttonPadding = size === 'sm' ? 'px-3 py-1.5' : 'px-4 py-2'
  const iconSize = size === 'sm' ? 'h-4 w-4' : 'h-5 w-5'
  const textSize = size === 'sm' ? 'text-xs' : 'text-sm'

  return (
    <div className={`relative ${className}`} ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={`flex h-8 items-center justify-between gap-2 whitespace-nowrap rounded-full bg-white ${buttonPadding} ${textSize} font-medium text-zinc-900 ring-1 ring-zinc-900/10 transition hover:ring-zinc-900/20 focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:bg-white/5 dark:text-white dark:ring-inset dark:ring-white/10 dark:hover:ring-white/20`}
      >
        <span>{selectedConfig?.label || t('evaluation.chartType.selectView')}</span>
        <ChevronDownIcon
          className={`h-4 w-4 shrink-0 opacity-70 transition-transform ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>

      {isOpen && (
        <div className="absolute left-0 z-50 mt-1 w-56 rounded-lg border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-800">
          <div className="py-1">
            {filteredTypes.map((chartType) => {
              const Icon = chartType.icon
              const isSelected = selectedType === chartType.type
              const isDisabled = disabledTypes.includes(chartType.type)
              const disabledReason = disabledReasons[chartType.type]

              return (
                <button
                  key={chartType.type}
                  type="button"
                  onClick={() => !isDisabled && handleSelect(chartType.type)}
                  disabled={isDisabled}
                  className={`flex w-full items-start gap-3 px-3 py-2 text-left ${textSize} ${
                    isSelected
                      ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400'
                      : isDisabled
                        ? 'cursor-not-allowed text-gray-400 dark:text-gray-500'
                        : 'text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-gray-700'
                  }`}
                  title={
                    isDisabled && disabledReason ? disabledReason : undefined
                  }
                >
                  <Icon className={`${iconSize} mt-0.5 flex-shrink-0`} />
                  <div className="flex-1">
                    <div className="font-medium">{chartType.label}</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      {chartType.description}
                    </div>
                  </div>
                  {isSelected && (
                    <span className="text-emerald-600 dark:text-emerald-400">
                      ✓
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

export { getChartTypes }
export type { ChartTypeConfig }
