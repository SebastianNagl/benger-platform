/**
 * File Upload Field Component
 *
 * File attachment field for the template system.
 *
 * Issue #216: Implement Unified Task Configuration and Display System
 */

import {
  CloudArrowUpIcon,
  DocumentIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import React, { useRef } from 'react'
import { useI18n } from '@/contexts/I18nContext'
import { BaseFieldProps, FieldWrapper } from './BaseField'

interface FileInfo {
  name: string
  size: number
  type: string
  url?: string
}

export function FileUploadField({
  field,
  value,
  onChange,
  readonly = false,
  errors = [],
  context,
  className = '',
}: BaseFieldProps) {
  const { t } = useI18n()
  const inputRef = useRef<HTMLInputElement>(null)
  const currentFile = value as FileInfo | null

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      const fileInfo: FileInfo = {
        name: file.name,
        size: file.size,
        type: file.type,
      }

      // In a real implementation, this would upload the file and get a URL
      // For now, we just store the file info
      onChange(fileInfo)
    }
  }

  const handleRemove = () => {
    onChange(null)
    if (inputRef.current) {
      inputRef.current.value = ''
    }
  }

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  }

  return (
    <FieldWrapper field={field} errors={errors} className={className}>
      {!currentFile ? (
        <div className="flex justify-center rounded-md border-2 border-dashed border-gray-300 px-6 pb-6 pt-5 dark:border-gray-600">
          <div className="space-y-1 text-center">
            <CloudArrowUpIcon className="mx-auto h-12 w-12 text-gray-400" />
            <div className="flex text-sm text-gray-600 dark:text-gray-400">
              <label
                htmlFor={field.name}
                className={`relative cursor-pointer rounded-md font-medium text-blue-600 focus-within:outline-none focus-within:ring-2 focus-within:ring-blue-500 focus-within:ring-offset-2 hover:text-blue-500 ${
                  readonly ? 'cursor-not-allowed opacity-50' : ''
                }`}
              >
                <span>{t('labeling.fileUpload.uploadFile')}</span>
                <input
                  ref={inputRef}
                  id={field.name}
                  name={field.name}
                  type="file"
                  className="sr-only"
                  onChange={handleFileSelect}
                  disabled={readonly}
                  accept={field.metadata?.accept}
                />
              </label>
              <p className="pl-1">{t('labeling.fileUpload.orDragAndDrop')}</p>
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {field.metadata?.accept || t('labeling.fileUpload.anyFileType')}
            </p>
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-between rounded-md border border-gray-300 p-4 dark:border-gray-600">
          <div className="flex items-center space-x-3">
            <DocumentIcon className="h-8 w-8 text-gray-400" />
            <div>
              <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                {currentFile.name}
              </p>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {formatFileSize(currentFile.size)}
              </p>
            </div>
          </div>
          {!readonly && (
            <button
              type="button"
              onClick={handleRemove}
              className="text-red-600 hover:text-red-500"
            >
              <XMarkIcon className="h-5 w-5" />
            </button>
          )}
        </div>
      )}
    </FieldWrapper>
  )
}
