/**
 * Base Field Component Interface
 *
 * Common interface and utilities for all field components in the template system.
 *
 * Issue #216: Implement Unified Task Configuration and Display System
 */

import { useI18n } from '@/contexts/I18nContext'
import { DisplayContext, TaskTemplateField } from '@/types/taskTemplate'
import { ExclamationCircleIcon } from '@heroicons/react/24/outline'
import React from 'react'

export interface BaseFieldProps<T = any> {
  field: TaskTemplateField
  value: T
  onChange: (value: T) => void
  readonly?: boolean
  errors?: string[]
  context: DisplayContext
  className?: string
}

export interface FieldWrapperProps {
  field: TaskTemplateField
  errors?: string[]
  children: React.ReactNode
  className?: string
}

/**
 * Field wrapper component that provides consistent layout and error handling
 */
export function FieldWrapper({
  field,
  errors,
  children,
  className = '',
}: FieldWrapperProps) {
  const { t } = useI18n()
  // Ensure optional fields are clearly marked as such
  const displayLabel = field.label
    ? field.required === false && !field.label.includes(t('fields.optional'))
      ? `${field.label} ${t('fields.optional')}`
      : field.label
    : field.label

  return (
    <div className={`field-wrapper ${className}`}>
      {displayLabel && (
        <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
          {displayLabel}
          {field.required && <span className="ml-1 text-red-500">*</span>}
        </label>
      )}

      {field.description && (
        <p className="mb-2 text-sm text-gray-500 dark:text-gray-400">
          {field.description}
        </p>
      )}

      {children}

      {errors && errors.length > 0 && (
        <div className="mt-1">
          {errors.map((error, index) => (
            <div
              key={index}
              className="flex items-center text-sm text-red-600 dark:text-red-400"
            >
              <ExclamationCircleIcon className="mr-1 h-4 w-4" />
              {error}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * Get common input classes based on state
 */
export function getInputClasses(hasError: boolean, readonly: boolean): string {
  const baseClasses =
    'block w-full rounded-md shadow-sm sm:text-sm transition-colors'

  const stateClasses = hasError
    ? 'border-red-300 dark:border-red-600 focus:border-red-500 focus:ring-red-500'
    : 'border-gray-300 dark:border-gray-600 focus:border-blue-500 focus:ring-blue-500'

  const readonlyClasses = readonly
    ? 'bg-gray-50 dark:bg-gray-800 cursor-not-allowed'
    : 'bg-white dark:bg-gray-700'

  return `${baseClasses} ${stateClasses} ${readonlyClasses}`
}

/**
 * Common validation for all fields
 */
export function validateFieldValue(
  field: TaskTemplateField,
  value: any
): string[] {
  const errors: string[] = []

  // Required validation
  if (field.required && !value) {
    errors.push(`${field.label || field.name} is required`)
  }

  // Field-specific validation is handled in individual components

  return errors
}
