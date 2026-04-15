'use client'

import { useEffect, useState } from 'react'
import { useI18n } from '@/contexts/I18nContext'
import { Listbox } from '@headlessui/react'
import {
  CheckIcon,
  ChevronDownIcon,
  ExclamationCircleIcon,
} from '@heroicons/react/24/outline'
import clsx from 'clsx'
import { projectsAPI } from '@/lib/api/projects'
import { LoadingSpinner } from './LoadingSpinner'

export interface TaskFieldInfo {
  path: string
  display_name: string
  sample_value: string
  data_type: string
  is_nested: boolean
}

interface TaskFieldSelectorProps {
  projectId: string
  value: string
  onChange: (path: string) => void
  placeholder?: string
  allowManualEntry?: boolean
  disabled?: boolean
  className?: string
}

export function TaskFieldSelector({
  projectId,
  value,
  onChange,
  placeholder,
  allowManualEntry = false,
  disabled = false,
  className,
}: TaskFieldSelectorProps) {
  const { t } = useI18n()
  const [fields, setFields] = useState<TaskFieldInfo[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [manualValue, setManualValue] = useState('')
  const [isManualMode, setIsManualMode] = useState(false)

  useEffect(() => {
    if (!projectId) return

    const fetchFields = async () => {
      setLoading(true)
      setError(null)
      try {
        const response = await projectsAPI.getTaskFields(projectId)
        setFields(response.fields)
      } catch (err) {
        setError(t('taskFields.fetchError', 'Failed to load available fields'))
        console.error('Failed to fetch task fields:', err)
      } finally {
        setLoading(false)
      }
    }

    fetchFields()
  }, [projectId, t])

  const topLevelFields = fields.filter((f) => !f.is_nested)
  const nestedFields = fields.filter((f) => f.is_nested)

  const selectedField = fields.find((f) => f.path === value)

  const handleManualSubmit = () => {
    if (manualValue.trim()) {
      const path = manualValue.startsWith('$')
        ? manualValue.trim()
        : `$${manualValue.trim()}`
      onChange(path)
      setIsManualMode(false)
      setManualValue('')
    }
  }

  if (loading) {
    return (
      <div
        className={clsx(
          'flex h-10 items-center gap-2 rounded-md border border-zinc-300 bg-white px-3 dark:border-zinc-700 dark:bg-zinc-800',
          className
        )}
      >
        <LoadingSpinner size="small" />
        <span className="text-sm text-zinc-500">
          {t('taskFields.loading', 'Loading fields...')}
        </span>
      </div>
    )
  }

  if (error) {
    return (
      <div
        className={clsx(
          'flex h-10 items-center gap-2 rounded-md border border-red-300 bg-red-50 px-3 dark:border-red-700 dark:bg-red-900/20',
          className
        )}
      >
        <ExclamationCircleIcon className="h-5 w-5 text-red-500" />
        <span className="text-sm text-red-600 dark:text-red-400">{error}</span>
      </div>
    )
  }

  if (allowManualEntry && isManualMode) {
    return (
      <div className={clsx('flex gap-2', className)}>
        <input
          type="text"
          value={manualValue}
          onChange={(e) => setManualValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              handleManualSubmit()
            } else if (e.key === 'Escape') {
              setIsManualMode(false)
              setManualValue('')
            }
          }}
          placeholder={t('taskFields.manualPlaceholder', 'e.g., $context.field')}
          className="flex-1 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 dark:border-zinc-700 dark:bg-zinc-800"
          autoFocus
        />
        <button
          onClick={handleManualSubmit}
          className="rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700"
        >
          {t('common.add', 'Add')}
        </button>
        <button
          onClick={() => {
            setIsManualMode(false)
            setManualValue('')
          }}
          className="rounded-md border border-zinc-300 px-3 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
        >
          {t('common.cancel', 'Cancel')}
        </button>
      </div>
    )
  }

  return (
    <div className={clsx('relative', className)}>
      <Listbox value={value} onChange={onChange} disabled={disabled}>
        <div className="relative">
          <Listbox.Button
            className={clsx(
              'relative w-full cursor-default rounded-md border border-zinc-300 bg-white py-2 pl-3 pr-10 text-left shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 dark:border-zinc-700 dark:bg-zinc-800 sm:text-sm',
              'disabled:cursor-not-allowed disabled:bg-zinc-50 disabled:text-zinc-500 dark:disabled:bg-zinc-900'
            )}
          >
            <span
              className={clsx(
                'block truncate',
                value
                  ? 'text-zinc-900 dark:text-white'
                  : 'text-zinc-500 dark:text-zinc-400'
              )}
            >
              {selectedField ? (
                <span className="flex items-center gap-2">
                  <code className="rounded bg-zinc-100 px-1 font-mono text-xs dark:bg-zinc-700">
                    {selectedField.path}
                  </code>
                  <span className="text-zinc-500 dark:text-zinc-400">
                    {selectedField.display_name}
                  </span>
                </span>
              ) : value ? (
                <code className="rounded bg-zinc-100 px-1 font-mono text-xs dark:bg-zinc-700">
                  {value}
                </code>
              ) : (
                placeholder || t('taskFields.selectField', 'Select a field...')
              )}
            </span>
            <span className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2">
              <ChevronDownIcon
                className="h-4 w-4 text-zinc-400"
                aria-hidden="true"
              />
            </span>
          </Listbox.Button>

          <Listbox.Options className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-md bg-white py-1 text-base shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none dark:bg-zinc-800 sm:text-sm">
            {fields.length === 0 ? (
              <div className="px-4 py-2 text-sm text-zinc-500">
                {t('taskFields.noFields', 'No fields found in task data')}
              </div>
            ) : (
              <>
                {topLevelFields.length > 0 && (
                  <div>
                    <div className="px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                      {t('taskFields.topLevelFields', 'Top-level Fields')}
                    </div>
                    {topLevelFields.map((field) => (
                      <FieldOption key={field.path} field={field} />
                    ))}
                  </div>
                )}

                {nestedFields.length > 0 && (
                  <div>
                    <div className="mt-2 border-t border-zinc-200 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
                      {t('taskFields.nestedFields', 'Nested Fields')}
                    </div>
                    {nestedFields.map((field) => (
                      <FieldOption key={field.path} field={field} />
                    ))}
                  </div>
                )}

                {allowManualEntry && (
                  <div className="mt-2 border-t border-zinc-200 dark:border-zinc-700">
                    <button
                      onClick={(e) => {
                        e.preventDefault()
                        setIsManualMode(true)
                      }}
                      className="w-full px-4 py-2 text-left text-sm text-emerald-600 hover:bg-emerald-50 dark:text-emerald-400 dark:hover:bg-emerald-900/20"
                    >
                      {t('taskFields.enterManually', 'Enter custom path...')}
                    </button>
                  </div>
                )}
              </>
            )}
          </Listbox.Options>
        </div>
      </Listbox>
    </div>
  )
}

interface FieldOptionProps {
  field: TaskFieldInfo
}

function FieldOption({ field }: FieldOptionProps) {
  return (
    <Listbox.Option
      value={field.path}
      className={({ active }) =>
        clsx(
          'relative cursor-default select-none py-2 pl-10 pr-4',
          active
            ? 'bg-emerald-100 text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100'
            : 'text-zinc-900 dark:text-zinc-100'
        )
      }
    >
      {({ selected }) => (
        <>
          <div className="flex flex-col">
            <div className="flex items-center gap-2">
              <code className="rounded bg-zinc-100 px-1 font-mono text-xs dark:bg-zinc-700">
                {field.path}
              </code>
              <span className="text-sm font-medium">{field.display_name}</span>
            </div>
            {field.sample_value && (
              <span className="mt-0.5 truncate text-xs text-zinc-500 dark:text-zinc-400">
                {field.sample_value}
              </span>
            )}
          </div>
          {selected && (
            <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-emerald-600 dark:text-emerald-400">
              <CheckIcon className="h-5 w-5" aria-hidden="true" />
            </span>
          )}
        </>
      )}
    </Listbox.Option>
  )
}
