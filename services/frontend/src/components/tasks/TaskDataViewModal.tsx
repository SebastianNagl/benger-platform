'use client'

import { useI18n } from '@/contexts/I18nContext'
import { projectsAPI } from '@/lib/api/projects'
import { Task } from '@/lib/api/types'
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/react'
import {
  ClipboardDocumentIcon,
  MagnifyingGlassIcon,
  PencilSquareIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { useEffect, useState } from 'react'

interface TaskDataViewModalProps {
  task: Task | null
  isOpen: boolean
  onClose: () => void
  /** Project id owning the task — required to persist edits. */
  projectId?: string
  /** Task id; defaults to `task.id` when omitted. */
  taskId?: string
  /** Open straight into edit mode (pencil) vs view mode (eye). */
  initialMode?: 'view' | 'edit'
  /** Whether the current user may edit — gates the Edit button and Save. */
  canEdit?: boolean
  /** Called after a successful save with the merged data fields. */
  onSaved?: (updatedData: Record<string, any>) => void
}

type ViewMode = 'formatted' | 'json'

/** Serialize task data into a per-field string buffer for editing. Strings stay
 * raw; everything else is edited as JSON. */
function buildEditBuffer(data: Record<string, any>): Record<string, string> {
  const buffer: Record<string, string> = {}
  Object.entries(data || {}).forEach(([key, value]) => {
    buffer[key] =
      typeof value === 'string' ? value : JSON.stringify(value, null, 2)
  })
  return buffer
}

/**
 * Modal component for viewing complete task data
 * Displays all task data fields in a formatted or raw JSON view
 */
export function TaskDataViewModal({
  task,
  isOpen,
  onClose,
  projectId,
  taskId,
  initialMode = 'view',
  canEdit = false,
  onSaved,
}: TaskDataViewModalProps) {
  const { t } = useI18n()
  const [viewMode, setViewMode] = useState<ViewMode>('formatted')
  const [searchTerm, setSearchTerm] = useState('')
  const [copySuccess, setCopySuccess] = useState(false)

  // Edit state
  const [mode, setMode] = useState<'view' | 'edit'>(
    canEdit ? initialMode : 'view'
  )
  const [editValues, setEditValues] = useState<Record<string, string>>({})
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  // Post-save overlay keyed by task id so display reflects edits immediately
  // without waiting for the parent to refetch; auto-resets when task changes.
  const [savedOverride, setSavedOverride] = useState<{
    id: string
    data: Record<string, any>
  } | null>(null)

  const baseData: Record<string, any> = ((task as any)?.data as Record<
    string,
    any
  >) || {}
  const currentTaskId = taskId ?? (task ? String(task.id) : '')
  const currentData =
    savedOverride && savedOverride.id === currentTaskId
      ? savedOverride.data
      : baseData

  // Reset transient edit state whenever the modal (re)opens or the task changes.
  useEffect(() => {
    if (!isOpen) return
    const startMode = canEdit ? initialMode : 'view'
    setMode(startMode)
    setSaveError(null)
    setFieldErrors({})
    if (startMode === 'edit') {
      setEditValues(buildEditBuffer(baseData))
    }
    // baseData intentionally omitted — keyed on task identity to avoid clobbering edits.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, currentTaskId, initialMode, canEdit])

  if (!task) return null

  const resolvedProjectId = projectId
  const canPersist = canEdit && !!resolvedProjectId && !!currentTaskId

  const enterEditMode = () => {
    setEditValues(buildEditBuffer(currentData))
    setFieldErrors({})
    setSaveError(null)
    setMode('edit')
  }

  const cancelEdit = () => {
    setFieldErrors({})
    setSaveError(null)
    setMode('view')
  }

  const handleFieldChange = (key: string, value: string) => {
    setEditValues((prev) => ({ ...prev, [key]: value }))
    if (fieldErrors[key]) {
      setFieldErrors((prev) => {
        const next = { ...prev }
        delete next[key]
        return next
      })
    }
  }

  const handleSave = async () => {
    if (!canPersist || !resolvedProjectId) return

    const newData: Record<string, any> = {}
    const errors: Record<string, string> = {}
    Object.entries(currentData).forEach(([key, original]) => {
      const raw = editValues[key] ?? ''
      if (typeof original === 'string') {
        newData[key] = raw
      } else {
        try {
          newData[key] = JSON.parse(raw)
        } catch {
          errors[key] = t('tasks.dataView.invalidJson')
        }
      }
    })

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors)
      return
    }

    setSaving(true)
    setSaveError(null)
    try {
      await projectsAPI.updateTaskData(resolvedProjectId, currentTaskId, newData)
      setSavedOverride({
        id: currentTaskId,
        data: { ...currentData, ...newData },
      })
      setMode('view')
      onSaved?.(newData)
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail ?? err?.detail ?? err?.message
      setSaveError(
        typeof detail === 'string' && detail
          ? detail
          : t('tasks.dataView.saveFailed')
      )
    } finally {
      setSaving(false)
    }
  }

  const isEditing = mode === 'edit'

  const handleCopyToClipboard = async () => {
    try {
      const textToCopy =
        viewMode === 'json'
          ? JSON.stringify(currentData, null, 2)
          : formatTaskDataAsText(currentData, searchTerm)

      await navigator.clipboard.writeText(textToCopy)
      // Only set success state after clipboard write succeeds
      setCopySuccess(true)
      setTimeout(() => setCopySuccess(false), 2000)
    } catch (error) {
      console.error('Failed to copy to clipboard:', error)
      // Ensure success state is not set on error
      setCopySuccess(false)
    }
  }

  const filteredData = searchTerm
    ? Object.entries(currentData).filter(
        ([key, value]) =>
          key.toLowerCase().includes(searchTerm.toLowerCase()) ||
          String(value).toLowerCase().includes(searchTerm.toLowerCase())
      )
    : Object.entries(currentData)

  return (
    <Dialog open={isOpen} onClose={onClose} className="relative z-50">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/30" aria-hidden="true" />

      {/* Full-screen container */}
      <div className="fixed inset-0 flex w-screen items-center justify-center p-4">
        <DialogPanel className="w-full max-w-4xl rounded-lg bg-white shadow-xl dark:bg-zinc-900">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-zinc-200 p-6 dark:border-zinc-700">
            <div>
              <DialogTitle className="text-lg font-semibold text-zinc-900 dark:text-white">
                {t('tasks.dataView.taskDataId', { id: task.id })}
              </DialogTitle>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                {t('tasks.dataView.taskType', {
                  type:
                    task.task_type ||
                    task.template_id ||
                    t('tasks.dataView.unknownType'),
                })}
              </p>
            </div>

            <div className="flex items-center gap-3">
              {isEditing ? (
                <>
                  {/* Save / Cancel */}
                  <button
                    onClick={handleSave}
                    disabled={saving}
                    className="flex items-center gap-2 rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {saving
                      ? t('tasks.dataView.saving')
                      : t('tasks.dataView.save')}
                  </button>
                  <button
                    onClick={cancelEdit}
                    disabled={saving}
                    className="rounded-md bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-200 disabled:opacity-60 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
                  >
                    {t('tasks.dataView.cancel')}
                  </button>
                </>
              ) : (
                <>
                  {/* View mode toggle */}
                  <div className="flex rounded-lg bg-zinc-100 p-1 dark:bg-zinc-800">
                    <button
                      onClick={() => setViewMode('formatted')}
                      className={`rounded-md px-3 py-1 text-sm font-medium transition-colors ${
                        viewMode === 'formatted'
                          ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white'
                          : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
                      }`}
                    >
                      {t('tasks.dataView.viewFormatted')}
                    </button>
                    <button
                      onClick={() => setViewMode('json')}
                      className={`rounded-md px-3 py-1 text-sm font-medium transition-colors ${
                        viewMode === 'json'
                          ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white'
                          : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
                      }`}
                    >
                      {t('tasks.dataView.viewJson')}
                    </button>
                  </div>

                  {/* Edit button */}
                  {canEdit && (
                    <button
                      onClick={enterEditMode}
                      className="flex items-center gap-2 rounded-md bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
                    >
                      <PencilSquareIcon className="h-4 w-4" />
                      {t('tasks.dataView.edit')}
                    </button>
                  )}

                  {/* Copy button */}
                  <button
                    onClick={handleCopyToClipboard}
                    className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                      copySuccess
                        ? 'bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400'
                        : 'bg-zinc-100 text-zinc-700 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700'
                    }`}
                  >
                    <ClipboardDocumentIcon className="h-4 w-4" />
                    {copySuccess
                      ? t('tasks.dataView.copied')
                      : t('tasks.dataView.copy')}
                  </button>
                </>
              )}

              {/* Close button */}
              <button
                onClick={onClose}
                className="rounded-lg p-2 text-zinc-600 transition-colors hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-white"
              >
                <XMarkIcon className="h-5 w-5" />
              </button>
            </div>
          </div>

          {/* Save error banner (edit mode) */}
          {isEditing && saveError && (
            <div className="border-b border-red-200 bg-red-50 px-6 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-400">
              {saveError}
            </div>
          )}

          {/* Search bar (only for formatted view) */}
          {!isEditing && viewMode === 'formatted' && (
            <div className="border-b border-zinc-200 p-6 dark:border-zinc-700">
              <div className="relative">
                <MagnifyingGlassIcon className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 transform text-zinc-400" />
                <input
                  type="text"
                  placeholder={t('tasks.dataView.searchPlaceholder')}
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full rounded-lg border border-zinc-300 bg-white py-2 pl-10 pr-4 text-zinc-900 placeholder-zinc-500 focus:border-blue-500 focus:ring-2 focus:ring-blue-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white dark:placeholder-zinc-400 dark:focus:border-blue-400"
                />
              </div>
            </div>
          )}

          {/* Content */}
          <div className="max-h-96 overflow-y-auto p-6">
            {isEditing ? (
              <EditableDataView
                data={currentData}
                editValues={editValues}
                fieldErrors={fieldErrors}
                onChange={handleFieldChange}
              />
            ) : viewMode === 'formatted' ? (
              <FormattedDataView data={filteredData} searchTerm={searchTerm} />
            ) : (
              <JsonDataView data={currentData} />
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between border-t border-zinc-200 p-6 text-sm text-zinc-600 dark:border-zinc-700 dark:text-zinc-400">
            <span>
              {searchTerm
                ? t('tasks.dataView.fieldsCountFiltered', {
                    count: Object.keys(currentData).length,
                    filtered: filteredData.length,
                  })
                : t('tasks.dataView.fieldsCount', {
                    count: Object.keys(currentData).length,
                  })}
            </span>
            <span>
              {t('tasks.dataView.created', {
                date: new Date(task.created_at).toLocaleString(),
              })}
            </span>
          </div>
        </DialogPanel>
      </div>
    </Dialog>
  )
}

interface FormattedDataViewProps {
  data: [string, any][]
  searchTerm: string
}

function FormattedDataView({ data, searchTerm }: FormattedDataViewProps) {
  const { t } = useI18n()

  if (data.length === 0) {
    return (
      <div className="py-8 text-center text-zinc-500 dark:text-zinc-400">
        {searchTerm
          ? t('tasks.dataView.noFieldsMatch')
          : t('tasks.dataView.noDataAvailable')}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {data.map(([key, value]) => (
        <div
          key={key}
          className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-700"
        >
          <div className="mb-2 flex items-center gap-2">
            <span className="font-medium text-zinc-900 dark:text-white">
              {highlightMatch(key, searchTerm)}
            </span>
            <span className="rounded bg-zinc-100 px-2 py-1 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
              {getValueType(value)}
            </span>
          </div>
          <div className="text-zinc-700 dark:text-zinc-300">
            {formatValueForDisplay(value, searchTerm)}
          </div>
        </div>
      ))}
    </div>
  )
}

interface JsonDataViewProps {
  data: Record<string, any>
}

function JsonDataView({ data }: JsonDataViewProps) {
  return (
    <pre className="overflow-x-auto rounded-lg bg-zinc-50 p-4 text-sm dark:bg-zinc-800">
      <code className="text-zinc-900 dark:text-white">
        {JSON.stringify(data, null, 2)}
      </code>
    </pre>
  )
}

interface EditableDataViewProps {
  data: Record<string, any>
  editValues: Record<string, string>
  fieldErrors: Record<string, string>
  onChange: (key: string, value: string) => void
}

function EditableDataView({
  data,
  editValues,
  fieldErrors,
  onChange,
}: EditableDataViewProps) {
  const { t } = useI18n()
  const entries = Object.entries(data)

  if (entries.length === 0) {
    return (
      <div className="py-8 text-center text-zinc-500 dark:text-zinc-400">
        {t('tasks.dataView.noDataAvailable')}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {entries.map(([key, value]) => {
        const isString = typeof value === 'string'
        const error = fieldErrors[key]
        return (
          <div
            key={key}
            className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-700"
          >
            <div className="mb-2 flex items-center gap-2">
              <span className="font-medium text-zinc-900 dark:text-white">
                {key}
              </span>
              <span className="rounded bg-zinc-100 px-2 py-1 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                {getValueType(value)}
              </span>
            </div>
            <textarea
              value={editValues[key] ?? ''}
              onChange={(e) => onChange(key, e.target.value)}
              rows={isString ? 3 : 5}
              spellCheck={false}
              className={`w-full rounded-lg border bg-white px-3 py-2 text-sm text-zinc-900 focus:ring-2 focus:ring-blue-500 dark:bg-zinc-800 dark:text-white ${
                error
                  ? 'border-red-400 focus:border-red-500 dark:border-red-500'
                  : 'border-zinc-300 focus:border-blue-500 dark:border-zinc-600 dark:focus:border-blue-400'
              } ${isString ? '' : 'font-mono'}`}
            />
            {error && (
              <p className="mt-1 text-xs text-red-600 dark:text-red-400">
                {error}
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}

function highlightMatch(text: string, searchTerm: string) {
  if (!searchTerm) return text

  const parts = text.split(new RegExp(`(${searchTerm})`, 'gi'))
  return parts.map((part, index) =>
    part.toLowerCase() === searchTerm.toLowerCase() ? (
      <mark key={index} className="bg-yellow-200 dark:bg-yellow-800">
        {part}
      </mark>
    ) : (
      part
    )
  )
}

function formatValueForDisplay(
  value: any,
  searchTerm: string
): React.ReactNode {
  if (value === null || value === undefined) {
    return <span className="italic text-zinc-500 dark:text-zinc-400">null</span>
  }

  if (Array.isArray(value)) {
    return (
      <div className="space-y-1">
        {value.map((item, index) => (
          <div key={index} className="flex items-center gap-2">
            <span className="text-zinc-500 dark:text-zinc-400">{index}:</span>
            <span>{highlightMatch(String(item), searchTerm)}</span>
          </div>
        ))}
      </div>
    )
  }

  if (typeof value === 'object') {
    return (
      <div className="space-y-1">
        {Object.entries(value).map(([k, v]) => (
          <div key={k} className="flex items-center gap-2">
            <span className="text-zinc-500 dark:text-zinc-400">{k}:</span>
            <span>{highlightMatch(String(v), searchTerm)}</span>
          </div>
        ))}
      </div>
    )
  }

  return (
    <span className={typeof value === 'string' ? 'break-words' : ''}>
      {highlightMatch(String(value), searchTerm)}
    </span>
  )
}

function getValueType(value: any): string {
  if (value === null || value === undefined) return 'null'
  if (Array.isArray(value)) return 'array'
  return typeof value
}

function formatTaskDataAsText(
  data: Record<string, any>,
  searchTerm: string
): string {
  const filteredEntries = searchTerm
    ? Object.entries(data).filter(
        ([key, value]) =>
          key.toLowerCase().includes(searchTerm.toLowerCase()) ||
          String(value).toLowerCase().includes(searchTerm.toLowerCase())
      )
    : Object.entries(data)

  return filteredEntries
    .map(([key, value]) => `${key}: ${JSON.stringify(value, null, 2)}`)
    .join('\n\n')
}
