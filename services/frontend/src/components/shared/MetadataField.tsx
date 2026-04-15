/**
 * MetadataField - Simple inline editing for task metadata
 * Label Studio aligned approach - treats all metadata fields equally
 *
 * Replaces the complex TagManager with direct, simple editing
 */

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import apiClient from '@/lib/api'
import { CheckIcon, PlusIcon, XMarkIcon } from '@heroicons/react/24/outline'
import React, { useEffect, useRef, useState } from 'react'

interface MetadataFieldProps {
  taskId: number
  fieldName: string
  value: any
  onUpdate?: (newValue: any) => void
  editable?: boolean
  className?: string
}

export function MetadataField({
  taskId,
  fieldName,
  value,
  onUpdate,
  editable = true,
  className = '',
}: MetadataFieldProps) {
  const { t } = useI18n()
  const [isEditing, setIsEditing] = useState(false)
  const [editValue, setEditValue] = useState(value)
  const [isLoading, setIsLoading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const { addToast } = useToast()

  useEffect(() => {
    setEditValue(value)
  }, [value])

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [isEditing])

  const handleSave = async () => {
    if (editValue === value) {
      setIsEditing(false)
      return
    }

    setIsLoading(true)
    try {
      // Use the new simplified metadata endpoint
      await apiClient.patch(`/api/projects/tasks/${taskId}/metadata`, {
        [fieldName]: editValue,
      })

      onUpdate?.(editValue)
      setIsEditing(false)
      addToast(t('shared.metadata.updated'), 'success')
    } catch (error) {
      console.error('Failed to update metadata:', error)
      addToast(t('shared.metadata.failedUpdate'), 'error')
      setEditValue(value) // Reset to original value
    } finally {
      setIsLoading(false)
    }
  }

  const handleCancel = () => {
    setEditValue(value)
    setIsEditing(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSave()
    } else if (e.key === 'Escape') {
      handleCancel()
    }
  }

  const renderValue = () => {
    // Handle different types of values
    if (Array.isArray(value)) {
      return (
        <div className="flex items-center gap-1 overflow-hidden">
          {value.length === 0 ? (
            <span className="text-sm text-zinc-400 dark:text-zinc-500">
              {t('shared.metadata.noItems', { field: fieldName })}
            </span>
          ) : (
            <>
              {value.slice(0, 2).map((item, index) => (
                <span
                  key={index}
                  className="inline-flex items-center whitespace-nowrap rounded bg-zinc-100 px-1.5 py-0 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                >
                  {item.length > 10 ? item.substring(0, 10) + '...' : item}
                </span>
              ))}
              {value.length > 2 && (
                <span className="text-xs text-zinc-500 dark:text-zinc-400">
                  +{value.length - 2}
                </span>
              )}
            </>
          )}
        </div>
      )
    } else if (typeof value === 'boolean') {
      return (
        <span
          className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${
            value
              ? 'bg-green-100 text-green-700 dark:bg-green-900/20 dark:text-green-400'
              : 'bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400'
          }`}
        >
          {value ? t('shared.metadata.yes') : t('shared.metadata.no')}
        </span>
      )
    } else if (value === null || value === undefined) {
      return <span className="text-sm text-zinc-400 dark:text-zinc-500">—</span>
    } else {
      return (
        <span className="text-zinc-900 dark:text-white">{String(value)}</span>
      )
    }
  }

  const renderEditInput = () => {
    // For arrays (like tags), show a comma-separated input
    if (Array.isArray(value)) {
      return (
        <input
          ref={inputRef}
          type="text"
          value={Array.isArray(editValue) ? editValue.join(', ') : ''}
          onChange={(e) => {
            const newValue = e.target.value
              .split(',')
              .map((s) => s.trim())
              .filter((s) => s.length > 0)
            setEditValue(newValue)
          }}
          onKeyDown={handleKeyDown}
          className="rounded-md border px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:border-zinc-700 dark:bg-zinc-800"
          placeholder={t('shared.metadata.enterCommaSeparated', { field: fieldName })}
          disabled={isLoading}
        />
      )
    } else if (typeof value === 'boolean') {
      return (
        <Select
          value={String(editValue)}
          onValueChange={(v) => setEditValue(v === 'true')}
          disabled={isLoading}
          displayValue={editValue ? t('shared.metadata.yes') : t('shared.metadata.no')}
        >
          <SelectTrigger className="h-7 w-auto min-w-[5rem] text-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="true">{t('shared.metadata.yes')}</SelectItem>
            <SelectItem value="false">{t('shared.metadata.no')}</SelectItem>
          </SelectContent>
        </Select>
      )
    } else {
      return (
        <input
          ref={inputRef}
          type="text"
          value={editValue || ''}
          onChange={(e) => setEditValue(e.target.value)}
          onKeyDown={handleKeyDown}
          className="rounded-md border px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:border-zinc-700 dark:bg-zinc-800"
          placeholder={t('shared.metadata.enterField', { field: fieldName })}
          disabled={isLoading}
        />
      )
    }
  }

  if (!editable) {
    return <div className={className}>{renderValue()}</div>
  }

  return (
    <div
      className={`inline-flex items-center gap-2 ${className}`}
      onClick={(e) => e.stopPropagation()}
    >
      {isEditing ? (
        <>
          {renderEditInput()}
          <button
            onClick={(e) => {
              e.stopPropagation()
              handleSave()
            }}
            disabled={isLoading}
            className="p-1 text-green-600 hover:text-green-700 disabled:opacity-50 dark:text-green-400 dark:hover:text-green-300"
            title={t('shared.metadata.save')}
          >
            <CheckIcon className="h-4 w-4" />
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation()
              handleCancel()
            }}
            disabled={isLoading}
            className="p-1 text-red-600 hover:text-red-700 disabled:opacity-50 dark:text-red-400 dark:hover:text-red-300"
            title={t('shared.metadata.cancel')}
          >
            <XMarkIcon className="h-4 w-4" />
          </button>
        </>
      ) : (
        <>
          {renderValue()}
          {(value === null ||
            value === undefined ||
            (Array.isArray(value) && value.length === 0)) && (
            <button
              onClick={(e) => {
                e.stopPropagation()
                setIsEditing(true)
              }}
              className="p-1 text-zinc-400 hover:text-zinc-600 dark:text-zinc-500 dark:hover:text-zinc-300"
              title={t('shared.metadata.addField', { field: fieldName })}
            >
              <PlusIcon className="h-4 w-4" />
            </button>
          )}
        </>
      )}
    </div>
  )
}

/**
 * BulkMetadataEditor - Simple form for bulk metadata updates
 * Replaces complex tag management with straightforward metadata editing
 */
export function BulkMetadataEditor({
  taskIds,
  onClose,
  onSuccess,
}: {
  taskIds: number[]
  onClose: () => void
  onSuccess?: () => void
}) {
  const { t } = useI18n()
  const [metadata, setMetadata] = useState<Record<string, any>>({})
  const [isLoading, setIsLoading] = useState(false)
  const { addToast } = useToast()

  const handleSubmit = async () => {
    if (Object.keys(metadata).length === 0) {
      addToast(t('shared.metadata.noMetadataToUpdate'), 'warning')
      return
    }

    setIsLoading(true)
    try {
      await apiClient.patch('/api/projects/tasks/bulk-metadata', {
        task_ids: taskIds,
        metadata,
      })

      addToast(t('shared.metadata.bulkUpdated', { count: taskIds.length }), 'success')
      onSuccess?.()
      onClose()
    } catch (error) {
      console.error('Failed to update metadata:', error)
      addToast(t('shared.metadata.failedUpdate'), 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const addField = (fieldName: string, value: any) => {
    setMetadata((prev) => ({
      ...prev,
      [fieldName]: value,
    }))
  }

  const removeField = (fieldName: string) => {
    setMetadata((prev) => {
      const newMeta = { ...prev }
      delete newMeta[fieldName]
      return newMeta
    })
  }

  return (
    <div className="rounded-lg bg-white p-4 shadow-lg dark:bg-zinc-900">
      <h3 className="mb-4 text-lg font-semibold">
        {t('shared.metadata.bulkEditTitle', { count: taskIds.length })}
      </h3>

      <div className="mb-4 space-y-3">
        {/* Common metadata fields */}
        <div className="flex items-center gap-2">
          <label className="w-24 text-sm font-medium">{t('shared.metadata.labelTags')}</label>
          <input
            type="text"
            placeholder={t('shared.metadata.tagsPlaceholder')}
            onChange={(e) => {
              const tags = e.target.value
                .split(',')
                .map((s) => s.trim())
                .filter((s) => s.length > 0)
              if (tags.length > 0) {
                addField('tags', tags)
              } else {
                removeField('tags')
              }
            }}
            className="flex-1 rounded-md border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:border-zinc-700 dark:bg-zinc-800"
          />
        </div>

        <div className="flex items-center gap-2">
          <label className="w-24 text-sm font-medium">{t('shared.metadata.labelPriority')}</label>
          <div className="flex-1">
            <Select
              value={metadata.priority || ''}
              onValueChange={(v) => {
                if (v) {
                  addField('priority', v)
                } else {
                  removeField('priority')
                }
              }}
              displayValue={
                metadata.priority === 'low' ? t('shared.metadata.priorityLow') :
                metadata.priority === 'medium' ? t('shared.metadata.priorityMedium') :
                metadata.priority === 'high' ? t('shared.metadata.priorityHigh') :
                metadata.priority === 'urgent' ? t('shared.metadata.priorityUrgent') :
                undefined
              }
            >
              <SelectTrigger>
                <SelectValue placeholder={t('shared.metadata.selectDefault')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="low">{t('shared.metadata.priorityLow')}</SelectItem>
                <SelectItem value="medium">{t('shared.metadata.priorityMedium')}</SelectItem>
                <SelectItem value="high">{t('shared.metadata.priorityHigh')}</SelectItem>
                <SelectItem value="urgent">{t('shared.metadata.priorityUrgent')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <label className="w-24 text-sm font-medium">{t('shared.metadata.labelStatus')}</label>
          <div className="flex-1">
            <Select
              value={metadata.status || ''}
              onValueChange={(v) => {
                if (v) {
                  addField('status', v)
                } else {
                  removeField('status')
                }
              }}
              displayValue={
                metadata.status === 'pending' ? t('shared.metadata.statusPending') :
                metadata.status === 'in_progress' ? t('shared.metadata.statusInProgress') :
                metadata.status === 'review' ? t('shared.metadata.statusReview') :
                metadata.status === 'completed' ? t('shared.metadata.statusCompleted') :
                undefined
              }
            >
              <SelectTrigger>
                <SelectValue placeholder={t('shared.metadata.selectDefault')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="pending">{t('shared.metadata.statusPending')}</SelectItem>
                <SelectItem value="in_progress">{t('shared.metadata.statusInProgress')}</SelectItem>
                <SelectItem value="review">{t('shared.metadata.statusReview')}</SelectItem>
                <SelectItem value="completed">{t('shared.metadata.statusCompleted')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      {Object.keys(metadata).length > 0 && (
        <div className="mb-4 rounded-md bg-zinc-50 p-3 dark:bg-zinc-800/50">
          <p className="mb-2 text-xs font-medium text-zinc-600 dark:text-zinc-400">
            {t('shared.metadata.metadataToUpdate')}
          </p>
          <pre className="text-xs text-zinc-700 dark:text-zinc-300">
            {JSON.stringify(metadata, null, 2)}
          </pre>
        </div>
      )}

      <div className="flex justify-end gap-2">
        <button
          onClick={onClose}
          className="rounded-md px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
        >
          {t('common.cancel')}
        </button>
        <button
          onClick={handleSubmit}
          disabled={isLoading || Object.keys(metadata).length === 0}
          className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isLoading ? t('shared.metadata.updating') : t('shared.metadata.updateMetadata')}
        </button>
      </div>
    </div>
  )
}
