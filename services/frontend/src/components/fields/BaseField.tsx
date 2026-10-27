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
        <label className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
          {displayLabel}
          {field.required && <span className="ml-1 text-red-500">*</span>}
        </label>
      )}

      {field.description && (
        <p className="mb-2 text-sm text-zinc-500 dark:text-zinc-400">
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
export function getInputClasses(
  hasError: boolean,
  readonly: boolean,
  multiline = false,
): string {
  // Same field style as the shared Input (a ring; preflight zeroes borders).
  const baseClasses =
    'block w-full px-4 py-2 text-base text-zinc-900 ring-1 transition placeholder:text-zinc-500 focus:ring-2 focus:outline-none sm:text-sm dark:text-white dark:ring-inset dark:placeholder:text-zinc-400'

  const stateClasses = hasError
    ? 'ring-red-300 focus:ring-red-500 dark:ring-red-600'
    : 'ring-zinc-900/10 hover:ring-zinc-900/20 focus:ring-emerald-500 dark:ring-white/10 dark:hover:ring-white/20 dark:focus:ring-emerald-400'

  const readonlyClasses = readonly
    ? 'bg-zinc-50 dark:bg-white/2.5 cursor-not-allowed'
    : 'bg-white dark:bg-white/5'

  const shapeClasses = multiline ? 'rounded-2xl' : 'rounded-full'

  return `${baseClasses} ${shapeClasses} ${stateClasses} ${readonlyClasses}`
}

/**
 * Common validation for all fields
 */
export function validateFieldValue(
  field: TaskTemplateField,
  value: any,
): string[] {
  const errors: string[] = []

  // Required validation
  if (field.required && !value) {
    errors.push(`${field.label || field.name} is required`)
  }

  // Field-specific validation is handled in individual components

  return errors
}
