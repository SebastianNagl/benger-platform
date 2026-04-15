'use client'

import { useCallback, useEffect, useState } from 'react'
import { useI18n } from '@/contexts/I18nContext'
import {
  PlusIcon,
  TrashIcon,
  InformationCircleIcon,
} from '@heroicons/react/24/outline'
import clsx from 'clsx'
import {
  TaskFieldSelector,
  TaskFieldInfo,
} from '@/components/shared/TaskFieldSelector'
import { projectsAPI } from '@/lib/api/projects'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'

interface FieldMappingEditorProps {
  projectId: string
  value: Record<string, string>
  onChange: (mappings: Record<string, string>) => void
}

interface MappingRow {
  id: string
  variableName: string
  fieldPath: string
}

const RESERVED_VARIABLES = [
  'context',
  'ground_truth',
  'prediction',
  'criterion_name',
  'criterion_description',
  'score_rubric',
  'answer_type_description',
]

export function FieldMappingEditor({
  projectId,
  value,
  onChange,
}: FieldMappingEditorProps) {
  const { t } = useI18n()
  const [rows, setRows] = useState<MappingRow[]>([])
  const [fields, setFields] = useState<TaskFieldInfo[]>([])
  const [loading, setLoading] = useState(false)

  // Sync rows from value prop
  useEffect(() => {
    const mappings = Object.entries(value || {}).map(
      ([variableName, fieldPath], index) => ({
        id: `mapping-${index}-${Date.now()}`,
        variableName,
        fieldPath,
      })
    )
    setRows(mappings.length > 0 ? mappings : [])
  }, [value])

  // Fetch available fields for reference
  useEffect(() => {
    if (!projectId) return

    const fetchFields = async () => {
      setLoading(true)
      try {
        const response = await projectsAPI.getTaskFields(projectId)
        setFields(response.fields)
      } catch (err) {
        console.error('Failed to fetch task fields:', err)
      } finally {
        setLoading(false)
      }
    }

    fetchFields()
  }, [projectId])

  // Emit changes when rows change
  const emitChanges = useCallback(
    (updatedRows: MappingRow[]) => {
      const mappings: Record<string, string> = {}
      updatedRows.forEach((row) => {
        if (row.variableName && row.fieldPath) {
          mappings[row.variableName] = row.fieldPath
        }
      })
      onChange(mappings)
    },
    [onChange]
  )

  const addRow = () => {
    const newRow: MappingRow = {
      id: `mapping-${Date.now()}`,
      variableName: '',
      fieldPath: '',
    }
    setRows((prev) => [...prev, newRow])
  }

  const removeRow = (id: string) => {
    setRows((prev) => {
      const updated = prev.filter((row) => row.id !== id)
      emitChanges(updated)
      return updated
    })
  }

  const updateRow = (id: string, field: keyof MappingRow, value: string) => {
    setRows((prev) => {
      const updated = prev.map((row) =>
        row.id === id ? { ...row, [field]: value } : row
      )
      emitChanges(updated)
      return updated
    })
  }

  const isReservedVariable = (name: string) => {
    return RESERVED_VARIABLES.includes(name.toLowerCase())
  }

  const getVariablePreview = (name: string) => {
    if (!name) return ''
    return `{{${name}}}`
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">
            {t('fieldMapping.title', 'Custom Field Mappings')}
          </h4>
          {loading && <LoadingSpinner size="small" />}
        </div>
        <button
          type="button"
          onClick={addRow}
          className="flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-600 hover:bg-emerald-100 dark:bg-emerald-900/20 dark:text-emerald-400 dark:hover:bg-emerald-900/40"
        >
          <PlusIcon className="h-4 w-4" />
          {t('fieldMapping.addMapping', 'Add Mapping')}
        </button>
      </div>

      <p className="text-xs text-gray-500 dark:text-gray-400">
        {t(
          'fieldMapping.helpText',
          'Map custom template variables to task data fields. Use {{variable_name}} in your prompt.'
        )}
      </p>

      {rows.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 p-4 text-center dark:border-gray-600">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {t(
              'fieldMapping.noMappings',
              'No field mappings defined. Click "Add Mapping" to create one.'
            )}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {/* Header row */}
          <div className="grid grid-cols-[1fr_auto_1fr_auto] gap-2 text-xs font-medium text-gray-500 dark:text-gray-400">
            <div>{t('fieldMapping.variableName', 'Variable Name')}</div>
            <div></div>
            <div>{t('fieldMapping.taskField', 'Task Data Field')}</div>
            <div></div>
          </div>

          {/* Mapping rows */}
          {rows.map((row) => {
            const hasError =
              row.variableName && isReservedVariable(row.variableName)
            const hasWarning = row.variableName && !row.fieldPath

            return (
              <div
                key={row.id}
                className={clsx(
                  'grid grid-cols-[1fr_auto_1fr_auto] items-center gap-2 rounded-lg border p-2',
                  hasError
                    ? 'border-red-300 bg-red-50 dark:border-red-700 dark:bg-red-900/20'
                    : hasWarning
                      ? 'border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-900/20'
                      : 'border-gray-200 dark:border-gray-700'
                )}
              >
                {/* Variable name input */}
                <div className="flex flex-col gap-1">
                  <input
                    type="text"
                    value={row.variableName}
                    onChange={(e) => {
                      // Sanitize: only allow alphanumeric and underscore
                      const sanitized = e.target.value.replace(
                        /[^a-zA-Z0-9_]/g,
                        ''
                      )
                      updateRow(row.id, 'variableName', sanitized)
                    }}
                    placeholder={t('fieldMapping.variablePlaceholder', 'domain')}
                    className={clsx(
                      'w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-1',
                      hasError
                        ? 'border-red-300 focus:border-red-500 focus:ring-red-500 dark:border-red-700'
                        : 'border-gray-300 focus:border-emerald-500 focus:ring-emerald-500 dark:border-gray-600 dark:bg-gray-800'
                    )}
                  />
                  {row.variableName && (
                    <span
                      className={clsx(
                        'text-xs',
                        hasError
                          ? 'text-red-600 dark:text-red-400'
                          : 'text-gray-500 dark:text-gray-400'
                      )}
                    >
                      {hasError
                        ? t('fieldMapping.reservedVariable', 'Reserved variable name')
                        : getVariablePreview(row.variableName)}
                    </span>
                  )}
                </div>

                {/* Arrow */}
                <div className="px-2 text-gray-400">
                  <span className="text-lg">&rarr;</span>
                </div>

                {/* Field selector */}
                <TaskFieldSelector
                  projectId={projectId}
                  value={row.fieldPath}
                  onChange={(path) => updateRow(row.id, 'fieldPath', path)}
                  placeholder={t('fieldMapping.selectField', 'Select a field...')}
                  allowManualEntry={true}
                />

                {/* Delete button */}
                <button
                  type="button"
                  onClick={() => removeRow(row.id)}
                  className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-red-600 dark:hover:bg-gray-800 dark:hover:text-red-400"
                  title={t('common.delete', 'Delete')}
                >
                  <TrashIcon className="h-4 w-4" />
                </button>
              </div>
            )
          })}
        </div>
      )}

      {/* Available fields reference */}
      {fields.length > 0 && (
        <div className="rounded-lg bg-gray-50 p-3 dark:bg-gray-800/50">
          <div className="mb-2 flex items-center gap-2 text-xs font-medium text-gray-600 dark:text-gray-400">
            <InformationCircleIcon className="h-4 w-4" />
            {t('fieldMapping.availableFields', 'Available fields in your tasks:')}
          </div>
          <div className="flex flex-wrap gap-1">
            {fields.slice(0, 10).map((field) => (
              <code
                key={field.path}
                className="rounded bg-gray-200 px-1.5 py-0.5 text-xs dark:bg-gray-700"
                title={field.sample_value}
              >
                {field.path}
              </code>
            ))}
            {fields.length > 10 && (
              <span className="text-xs text-gray-500">
                +{fields.length - 10} more
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
