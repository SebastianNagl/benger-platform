'use client'

import { Input } from '@/components/shared/Input'
import {
  Select,
  SelectContent,
  SelectGroupLabel,
  SelectItem,
  SelectTrigger,
} from '@/components/shared/Select'
import { useI18n } from '@/contexts/I18nContext'
import { projectsAPI } from '@/lib/api/projects'
import { ExclamationCircleIcon } from '@heroicons/react/24/outline'
import clsx from 'clsx'
import { useEffect, useState } from 'react'
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
        setError(t('taskFields.fetchError'))
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
          className,
        )}
      >
        <LoadingSpinner size="small" />
        <span className="text-sm text-zinc-500">{t('taskFields.loading')}</span>
      </div>
    )
  }

  if (error) {
    return (
      <div
        className={clsx(
          'flex h-10 items-center gap-2 rounded-md border border-red-300 bg-red-50 px-3 dark:border-red-700 dark:bg-red-900/20',
          className,
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
        <Input
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
          placeholder={t('taskFields.manualPlaceholder')}
          className="flex-1"
          autoFocus
        />
        <button
          onClick={handleManualSubmit}
          className="h-8 rounded-full bg-zinc-900 px-3 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-emerald-500 dark:hover:bg-emerald-400"
        >
          {t('common.add')}
        </button>
        <button
          onClick={() => {
            setIsManualMode(false)
            setManualValue('')
          }}
          className="h-8 rounded-full border border-zinc-300 px-3 text-sm font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
        >
          {t('common.cancel')}
        </button>
      </div>
    )
  }

  return (
    <div className={clsx('relative', className)}>
      <Select
        searchable
        value={value}
        onValueChange={onChange}
        disabled={disabled}
        emptyMessage={
          fields.length === 0 ? t('taskFields.noFields') : undefined
        }
      >
        <SelectTrigger>
          <span
            className={clsx(
              'block truncate',
              value
                ? 'text-zinc-900 dark:text-white'
                : 'text-zinc-500 dark:text-zinc-400',
            )}
          >
            {selectedField ? (
              <span className="flex items-center gap-2">
                <code className="rounded bg-zinc-100 px-1 font-mono text-xs dark:bg-zinc-700">
                  {selectedField.path}
                </code>
                <span className="truncate text-zinc-500 dark:text-zinc-400">
                  {selectedField.display_name}
                </span>
              </span>
            ) : value ? (
              <code className="rounded bg-zinc-100 px-1 font-mono text-xs dark:bg-zinc-700">
                {value}
              </code>
            ) : (
              placeholder || t('taskFields.selectField')
            )}
          </span>
        </SelectTrigger>

        <SelectContent>
          {topLevelFields.length > 0 && (
            <SelectGroupLabel>
              {t('taskFields.topLevelFields')}
            </SelectGroupLabel>
          )}
          {topLevelFields.map((field) => fieldOption(field))}

          {nestedFields.length > 0 && (
            <SelectGroupLabel>{t('taskFields.nestedFields')}</SelectGroupLabel>
          )}
          {nestedFields.map((field) => fieldOption(field))}

          {allowManualEntry && (
            <div className="mt-1 border-t border-zinc-200 dark:border-zinc-700">
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault()
                  setIsManualMode(true)
                }}
                className="w-full px-4 py-2 text-left text-sm text-emerald-600 hover:bg-emerald-50 dark:text-emerald-400 dark:hover:bg-emerald-900/20"
              >
                {t('taskFields.enterManually')}
              </button>
            </div>
          )}
        </SelectContent>
      </Select>
    </div>
  )
}

/** One field: its path and name sort and search; the sample is a hint. */
function fieldOption(field: TaskFieldInfo) {
  return (
    <SelectItem
      key={field.path}
      value={field.path}
      textValue={`${field.path} ${field.display_name}`}
    >
      <span className="flex flex-col">
        <span className="flex items-center gap-2">
          <code className="rounded bg-zinc-100 px-1 font-mono text-xs dark:bg-zinc-700">
            {field.path}
          </code>
          <span className="text-sm font-medium">{field.display_name}</span>
        </span>
        {field.sample_value && (
          <span className="mt-0.5 truncate text-xs font-normal text-zinc-500 dark:text-zinc-400">
            {field.sample_value}
          </span>
        )}
      </span>
    </SelectItem>
  )
}
