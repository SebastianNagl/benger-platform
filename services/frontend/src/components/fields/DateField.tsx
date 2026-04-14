/**
 * Date Field Component
 *
 * Date picker field for the template system.
 *
 * Issue #216: Implement Unified Task Configuration and Display System
 */

import React from 'react'
import { BaseFieldProps, FieldWrapper, getInputClasses } from './BaseField'

export function DateField({
  field,
  value,
  onChange,
  readonly = false,
  errors = [],
  context,
  className = '',
}: BaseFieldProps) {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange(e.target.value)
  }

  const hasError = errors.length > 0
  const inputClasses = getInputClasses(hasError, readonly)

  // Format value for date input (YYYY-MM-DD)
  const formattedValue = value
    ? (() => {
        try {
          const date = new Date(value)
          if (isNaN(date.getTime())) {
            return ''
          }
          return date.toISOString().split('T')[0]
        } catch {
          return ''
        }
      })()
    : ''

  return (
    <FieldWrapper field={field} errors={errors} className={className}>
      <input
        type="date"
        id={field.name}
        name={field.name}
        value={formattedValue}
        onChange={handleChange}
        disabled={readonly}
        className={inputClasses}
      />
    </FieldWrapper>
  )
}
