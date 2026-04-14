/**
 * Rich Text Field Component
 *
 * Formatted text editor field for the template system.
 *
 * Issue #216: Implement Unified Task Configuration and Display System
 */

import { useI18n } from '@/contexts/I18nContext'
import React, { useCallback } from 'react'
import { BaseFieldProps, FieldWrapper } from './BaseField'

export function RichTextField({
  field,
  value,
  onChange,
  readonly = false,
  errors = [],
  context,
  className = '',
}: BaseFieldProps) {
  const { t } = useI18n()
  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      onChange(e.target.value)
    },
    [onChange]
  )

  return (
    <FieldWrapper field={field} errors={errors} className={className}>
      <div className={`rich-text-editor ${readonly ? 'readonly' : ''}`}>
        <textarea
          value={value || ''}
          onChange={handleChange}
          readOnly={readonly}
          placeholder={field.placeholder}
          rows={6}
          className={`w-full rounded-md border px-3 py-2 text-sm shadow-sm ${
            readonly
              ? 'cursor-not-allowed bg-gray-50 dark:bg-gray-800'
              : 'bg-white dark:bg-gray-900'
          } ${
            errors.length > 0
              ? 'border-red-300 focus:border-red-500 focus:ring-red-500 dark:border-red-600'
              : 'border-gray-300 focus:border-blue-500 focus:ring-blue-500 dark:border-gray-600'
          } resize-vertical focus:outline-none focus:ring-2 dark:text-white`}
        />
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {t('fields.richTextPlaceholder')}
        </p>
      </div>
    </FieldWrapper>
  )
}
