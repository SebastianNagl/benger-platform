/**
 * Filter Dropdown component for the Project Data Manager
 *
 * Provides filtering options for tasks with Label Studio aligned metadata approach
 */

import { Button } from '@/components/shared/Button'
import { Input } from '@/components/shared/Input'
import { useI18n } from '@/contexts/I18nContext'
import apiClient from '@/lib/api'
import { Menu } from '@headlessui/react'
import {
  AdjustmentsHorizontalIcon,
  CalendarIcon,
  CheckIcon,
  ChevronDownIcon,
  FunnelIcon,
  UserIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { useCallback, useEffect, useState } from 'react'

interface FilterDropdownProps {
  projectId?: string
  filterStatus: 'all' | 'completed' | 'incomplete'
  onStatusChange: (status: 'all' | 'completed' | 'incomplete') => void
  onDateRangeChange?: (startDate: string, endDate: string) => void
  onAnnotatorChange?: (annotator: string) => void
  metadataFilters?: Record<string, any>
  onMetadataChange?: (filters: Record<string, any>) => void
}

interface MetadataField {
  name: string
  values: Array<{ value: any; count: number }>
  type: 'string' | 'array' | 'boolean' | 'number'
}

export function FilterDropdown({
  projectId,
  filterStatus,
  onStatusChange,
  onDateRangeChange,
  onAnnotatorChange,
  metadataFilters = {},
  onMetadataChange,
}: FilterDropdownProps) {
  const { t } = useI18n()

  const filterOptions = [
    { value: 'all' as const, label: t('projects.filter.allTasks') },
    { value: 'completed' as const, label: t('projects.filter.completed') },
    { value: 'incomplete' as const, label: t('projects.filter.incomplete') },
  ]
  const currentFilter = filterOptions.find(
    (option) => option.value === filterStatus
  )
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [annotatorFilter, setAnnotatorFilter] = useState('')
  const [availableMetadata, setAvailableMetadata] = useState<MetadataField[]>(
    []
  )
  const [localMetadataFilters, setLocalMetadataFilters] =
    useState<Record<string, any>>(metadataFilters)

  const fetchAvailableMetadata = useCallback(async () => {
    if (!projectId) return

    try {
      // Fetch tasks to analyze metadata fields
      const response = await apiClient.get(
        `/projects/${projectId}/tasks?limit=100`
      )
      const tasks = response.tasks || []

      // Analyze metadata structure
      const metadataMap = new Map<string, Map<any, number>>()
      const typeMap = new Map<string, string>()

      tasks.forEach((task: any) => {
        if (task.meta && typeof task.meta === 'object') {
          Object.entries(task.meta).forEach(([key, value]) => {
            if (!metadataMap.has(key)) {
              metadataMap.set(key, new Map())
              typeMap.set(key, Array.isArray(value) ? 'array' : typeof value)
            }

            const valueMap = metadataMap.get(key)!
            if (Array.isArray(value)) {
              value.forEach((v) => {
                valueMap.set(v, (valueMap.get(v) || 0) + 1)
              })
            } else {
              valueMap.set(value, (valueMap.get(value) || 0) + 1)
            }
          })
        }
      })

      // Convert to MetadataField format
      const fields: MetadataField[] = []
      metadataMap.forEach((valueMap, fieldName) => {
        const values = Array.from(valueMap.entries())
          .map(([value, count]) => ({ value, count }))
          .sort((a, b) => b.count - a.count)
          .slice(0, 10) // Top 10 values per field

        fields.push({
          name: fieldName,
          values,
          type: (typeMap.get(fieldName) || 'string') as any,
        })
      })

       
      setAvailableMetadata(fields)
    } catch (error) {
      // Silently fail - metadata is optional
       
      setAvailableMetadata([])
    }
  }, [projectId])

  useEffect(() => {
    if (projectId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- Intentional: trigger fetch on projectId change
      fetchAvailableMetadata()
    }
  }, [projectId, fetchAvailableMetadata])

  const toggleMetadataFilter = (fieldName: string, value: any) => {
    const newFilters = { ...localMetadataFilters }

    if (!newFilters[fieldName]) {
      newFilters[fieldName] = []
    }

    if (Array.isArray(newFilters[fieldName])) {
      const index = newFilters[fieldName].indexOf(value)
      if (index > -1) {
        newFilters[fieldName].splice(index, 1)
        if (newFilters[fieldName].length === 0) {
          delete newFilters[fieldName]
        }
      } else {
        newFilters[fieldName].push(value)
      }
    } else {
      if (newFilters[fieldName] === value) {
        delete newFilters[fieldName]
      } else {
        newFilters[fieldName] = value
      }
    }

    setLocalMetadataFilters(newFilters)
    onMetadataChange?.(newFilters)
  }

  const activeFilterCount = [
    filterStatus !== 'all' ? 1 : 0,
    startDate && endDate ? 1 : 0,
    annotatorFilter ? 1 : 0,
    Object.keys(localMetadataFilters).length > 0 ? 1 : 0,
  ].reduce((a, b) => a + b, 0)

  return (
    <Menu as="div" className="relative inline-block text-left">
      <div>
        <Menu.Button as={Button} variant="outline" className="gap-2">
          <FunnelIcon className="h-4 w-4" />
          {t('projects.filter.filters')}
          {activeFilterCount > 0 && (
            <span className="ml-1 inline-flex items-center rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200">
              {activeFilterCount}
            </span>
          )}
          <ChevronDownIcon className="h-4 w-4" />
        </Menu.Button>
      </div>

      <Menu.Items className="absolute left-0 z-10 mt-2 max-h-96 w-80 origin-top-left overflow-y-auto rounded-lg bg-white shadow-lg ring-1 ring-black ring-opacity-5 transition duration-100 ease-out focus:outline-none data-[closed]:scale-95 data-[closed]:transform data-[closed]:opacity-0 dark:bg-zinc-900">
        <div className="p-1">
          <div className="px-3 py-2 text-xs font-medium text-zinc-500 dark:text-zinc-400">
            {t('projects.filter.status')}
          </div>
          {filterOptions.map((option) => (
            <Menu.Item key={option.value}>
              {({ active }) => (
                <button
                  className={`${
                    active ? 'bg-zinc-100 dark:bg-zinc-800' : ''
                  } group flex w-full items-center rounded-md px-3 py-2 text-sm text-zinc-900 dark:text-white`}
                  onClick={() => onStatusChange(option.value)}
                >
                  <div className="flex w-full items-center justify-between">
                    <span>{option.label}</span>
                    {filterStatus === option.value && (
                      <CheckIcon className="h-4 w-4 text-emerald-600" />
                    )}
                  </div>
                </button>
              )}
            </Menu.Item>
          ))}

          <div className="my-1 border-t border-zinc-200 dark:border-zinc-700" />

          {/*  filter options */}
          <div className="my-1 border-t border-zinc-200 dark:border-zinc-700" />
          <div className="px-3 py-2 text-xs font-medium text-zinc-500 dark:text-zinc-400">
            {t('projects.filter.filters')}
          </div>

          {/* Date Range Filter */}
          <div className="px-3 py-2">
            <div className="mb-2 flex items-center">
              <CalendarIcon className="mr-2 h-4 w-4 text-zinc-500" />
              <span className="text-sm font-medium text-zinc-900 dark:text-white">
                {t('projects.filter.dateRange')}
              </span>
            </div>
            <div className="space-y-2">
              <Input
                type="date"
                placeholder={t('projects.filter.startDate')}
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="text-xs"
              />
              <Input
                type="date"
                placeholder={t('projects.filter.endDate')}
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="text-xs"
              />
              <Button
                variant="outline"
                className="w-full text-xs"
                onClick={() => {
                  if (startDate && endDate && onDateRangeChange) {
                    onDateRangeChange(startDate, endDate)
                  }
                }}
                disabled={!startDate || !endDate}
              >
                {t('projects.filter.applyDateFilter')}
              </Button>
            </div>
          </div>

          <div className="my-1 border-t border-zinc-200 dark:border-zinc-700" />

          {/* Annotator Filter */}
          <div className="px-3 py-2">
            <div className="mb-2 flex items-center">
              <UserIcon className="mr-2 h-4 w-4 text-zinc-500" />
              <span className="text-sm font-medium text-zinc-900 dark:text-white">
                {t('projects.filter.annotator')}
              </span>
            </div>
            <div className="space-y-2">
              <Input
                placeholder={t('projects.filter.annotatorPlaceholder')}
                value={annotatorFilter}
                onChange={(e) => setAnnotatorFilter(e.target.value)}
                className="text-xs"
              />
              <Button
                variant="outline"
                className="w-full text-xs"
                onClick={() => {
                  if (annotatorFilter && onAnnotatorChange) {
                    onAnnotatorChange(annotatorFilter)
                  }
                }}
                disabled={!annotatorFilter}
              >
                {t('projects.filter.applyAnnotatorFilter')}
              </Button>
            </div>
          </div>

          <div className="my-1 border-t border-zinc-200 dark:border-zinc-700" />

          {/* Metadata Filter */}
          <div className="px-3 py-2">
            <div className="mb-2 flex items-center">
              <AdjustmentsHorizontalIcon className="mr-2 h-4 w-4 text-zinc-500" />
              <span className="text-sm font-medium text-zinc-900 dark:text-white">
                {t('projects.filter.filterByMetadata')}
              </span>
            </div>

            {/* Active metadata filters */}
            {Object.keys(localMetadataFilters).length > 0 && (
              <div className="mb-3">
                <div className="mb-2 text-xs text-zinc-500 dark:text-zinc-400">
                  {t('projects.filter.activeFilters')}
                </div>
                <div className="space-y-1">
                  {Object.entries(localMetadataFilters).map(
                    ([field, values]) => (
                      <div key={field} className="text-xs">
                        <span className="font-medium text-zinc-700 dark:text-zinc-300">
                          {field}:
                        </span>
                        <div className="ml-2 mt-1 flex flex-wrap gap-1">
                          {(Array.isArray(values) ? values : [values]).map(
                            (value, idx) => (
                              <span
                                key={idx}
                                className="inline-flex items-center gap-1 rounded-md bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200"
                              >
                                {String(value)}
                                <button
                                  onClick={() =>
                                    toggleMetadataFilter(field, value)
                                  }
                                  className="hover:text-emerald-600 dark:hover:text-emerald-400"
                                  aria-label={t('projects.filter.removeFilter', { field, value: String(value) })}
                                >
                                  <XMarkIcon className="h-3 w-3" />
                                </button>
                              </span>
                            )
                          )}
                        </div>
                      </div>
                    )
                  )}
                </div>
              </div>
            )}

            {/* Available metadata fields */}
            <div className="space-y-2">
              {availableMetadata.length > 0 ? (
                <div className="space-y-2">
                  <span className="text-xs text-zinc-500 dark:text-zinc-400">
                    {t('projects.filter.availableMetadataFields')}
                  </span>
                  {availableMetadata.map((field) => (
                    <div
                      key={field.name}
                      className="border-t border-zinc-200 pt-2 dark:border-zinc-700"
                    >
                      <div className="mb-1 text-xs font-medium text-zinc-700 dark:text-zinc-300">
                        {field.name}
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {field.values.map((item, idx) => {
                          const isSelected = Array.isArray(
                            localMetadataFilters[field.name]
                          )
                            ? localMetadataFilters[field.name].includes(
                                item.value
                              )
                            : localMetadataFilters[field.name] === item.value

                          return (
                            <button
                              key={idx}
                              onClick={() =>
                                toggleMetadataFilter(field.name, item.value)
                              }
                              className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium transition-colors ${
                                isSelected
                                  ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200'
                                  : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-700'
                              }`}
                            >
                              {String(item.value)}
                              <span className="text-[10px] opacity-60">
                                ({item.count})
                              </span>
                            </button>
                          )
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="py-2 text-center text-xs text-zinc-500 dark:text-zinc-400">
                  {t('projects.filter.noMetadataFields')}
                </p>
              )}
            </div>
          </div>

          <div className="my-1 border-t border-zinc-200 dark:border-zinc-700" />

          {/* Clear All Filters */}
          <div className="px-3 py-2">
            <Button
              variant="outline"
              className="w-full text-xs text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20"
              onClick={() => {
                setStartDate('')
                setEndDate('')
                setAnnotatorFilter('')
                onStatusChange('all')
                setLocalMetadataFilters({})
                if (onDateRangeChange) onDateRangeChange('', '')
                if (onAnnotatorChange) onAnnotatorChange('')
                if (onMetadataChange) onMetadataChange({})
              }}
            >
              {t('projects.filter.clearAllFilters')}
            </Button>
          </div>
        </div>
      </Menu.Items>
    </Menu>
  )
}
