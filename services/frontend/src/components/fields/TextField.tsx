/**
 * Text Field Component
 *
 * Single-line text input field for the template system.
 *
 * Issue #216: Implement Unified Task Configuration and Display System
 */

import React from 'react'
import { BaseFieldProps, FieldWrapper, getInputClasses } from './BaseField'

export function TextField({
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

  return (
    <FieldWrapper field={field} errors={errors} className={className}>
      <input
        type="text"
        id={field.name}
        name={field.name}
        value={value || ''}
        onChange={handleChange}
        disabled={readonly}
        placeholder={field.placeholder}
        className={inputClasses}
        maxLength={field.validation?.find((v) => v.type === 'maxLength')?.value}
      />
    </FieldWrapper>
  )
}
