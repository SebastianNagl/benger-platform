'use client'

import { useEffect, useState } from 'react'
import { useI18n } from '@/contexts/I18nContext'
import {
  InformationCircleIcon,
  ClipboardDocumentIcon,
  ChevronDownIcon,
  ChevronRightIcon,
} from '@heroicons/react/24/outline'
import clsx from 'clsx'
import { projectsAPI } from '@/lib/api/projects'
import { LoadingSpinner } from './LoadingSpinner'

interface TaskFieldInfo {
  path: string
  display_name: string
  sample_value: string
  data_type: string
  is_nested: boolean
}

interface TaskFieldReferencePanelProps {
  projectId: string
  className?: string
  defaultExpanded?: boolean
  title?: string
  description?: string
}

export function TaskFieldReferencePanel({
  projectId,
  className,
  defaultExpanded = false,
  title,
  description,
}: TaskFieldReferencePanelProps) {
  const { t } = useI18n()
  const [fields, setFields] = useState<TaskFieldInfo[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(defaultExpanded)
  const [copiedPath, setCopiedPath] = useState<string | null>(null)

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

  const copyToClipboard = async (path: string) => {
    try {
      // For XML annotation config, copy without the $ prefix
      const valueToCopy = path.startsWith('$') ? path.substring(1) : path
      await navigator.clipboard.writeText(valueToCopy)
      setCopiedPath(path)
      setTimeout(() => setCopiedPath(null), 2000)
    } catch (err) {
      console.error('Failed to copy to clipboard:', err)
    }
  }

  const topLevelFields = fields.filter((f) => !f.is_nested)
  const nestedFields = fields.filter((f) => f.is_nested)

  return (
    <div
      className={clsx(
        'rounded-lg border border-zinc-200 bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800/50',
        className
      )}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-4 py-3 text-left"
      >
        <div className="flex items-center gap-2">
          <InformationCircleIcon className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
          <span className="text-sm font-medium text-zinc-900 dark:text-white">
            {title || t('taskFields.referenceTitle', 'Available Task Fields')}
          </span>
        </div>
        {expanded ? (
          <ChevronDownIcon className="h-5 w-5 text-zinc-500" />
        ) : (
          <ChevronRightIcon className="h-5 w-5 text-zinc-500" />
        )}
      </button>

      {expanded && (
        <div className="border-t border-zinc-200 px-4 py-3 dark:border-zinc-700">
          {description && (
            <p className="mb-3 text-sm text-zinc-600 dark:text-zinc-400">
              {description}
            </p>
          )}

          {loading ? (
            <div className="flex items-center gap-2 py-2">
              <LoadingSpinner size="small" />
              <span className="text-sm text-zinc-500">
                {t('taskFields.loading', 'Loading fields...')}
              </span>
            </div>
          ) : error ? (
            <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
          ) : fields.length === 0 ? (
            <p className="text-sm text-zinc-500">
              {t(
                'taskFields.noFieldsReference',
                'No fields found. Import tasks to see available fields.'
              )}
            </p>
          ) : (
            <div className="space-y-3">
              {topLevelFields.length > 0 && (
                <div>
                  <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                    {t('taskFields.topLevelFields', 'Top-level Fields')}
                  </h4>
                  <div className="flex flex-wrap gap-1.5">
                    {topLevelFields.map((field) => (
                      <FieldBadge
                        key={field.path}
                        field={field}
                        copied={copiedPath === field.path}
                        onCopy={() => copyToClipboard(field.path)}
                      />
                    ))}
                  </div>
                </div>
              )}

              {nestedFields.length > 0 && (
                <div>
                  <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                    {t('taskFields.nestedFields', 'Nested Fields')}
                  </h4>
                  <div className="flex flex-wrap gap-1.5">
                    {nestedFields.map((field) => (
                      <FieldBadge
                        key={field.path}
                        field={field}
                        copied={copiedPath === field.path}
                        onCopy={() => copyToClipboard(field.path)}
                      />
                    ))}
                  </div>
                </div>
              )}

              <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
                {t(
                  'taskFields.clickToCopy',
                  'Click a field name to copy it to clipboard'
                )}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

interface FieldBadgeProps {
  field: TaskFieldInfo
  copied: boolean
  onCopy: () => void
}

function FieldBadge({ field, copied, onCopy }: FieldBadgeProps) {
  const { t } = useI18n()
  // Display name without $ prefix for XML usage
  const displayPath = field.path.startsWith('$')
    ? field.path.substring(1)
    : field.path

  return (
    <button
      onClick={onCopy}
      className={clsx(
        'group relative inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs font-mono transition-colors',
        copied
          ? 'border-emerald-500 bg-emerald-100 text-emerald-700 dark:border-emerald-600 dark:bg-emerald-900/40 dark:text-emerald-400'
          : 'border-zinc-300 bg-white text-zinc-700 hover:border-emerald-400 hover:bg-emerald-50 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:border-emerald-500 dark:hover:bg-emerald-900/20'
      )}
      title={
        field.sample_value
          ? `${field.display_name}: ${field.sample_value}`
          : field.display_name
      }
    >
      {displayPath}
      <ClipboardDocumentIcon
        className={clsx(
          'h-3 w-3 transition-opacity',
          copied
            ? 'opacity-100'
            : 'opacity-0 group-hover:opacity-100 text-zinc-400'
        )}
      />
      {copied && (
        <span className="absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-zinc-900 px-2 py-1 text-xs text-white shadow-lg dark:bg-zinc-700">
          {t('common.copied')}
        </span>
      )}
    </button>
  )
}
