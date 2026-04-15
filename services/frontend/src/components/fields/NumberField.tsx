/**
 * Number Field Component
 *
 * Numeric input field for the template system.
 *
 * Issue #216: Implement Unified Task Configuration and Display System
 */

import React from 'react'
import { BaseFieldProps, FieldWrapper, getInputClasses } from './BaseField'

export function NumberField({
  field,
  value,
  onChange,
  readonly = false,
  errors = [],
  context,
  className = '',
}: BaseFieldProps) {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value
    if (newValue === '') {
      onChange(null)
    } else {
      const parsed = parseFloat(newValue)
      if (!isNaN(parsed)) {
        onChange(parsed)
      }
    }
  }

  const hasError = errors.length > 0
  const inputClasses = getInputClasses(hasError, readonly)

  const min = field.validation?.find((v) => v.type === 'min')?.value
  const max = field.validation?.find((v) => v.type === 'max')?.value

  return (
    <FieldWrapper field={field} errors={errors} className={className}>
      <input
        type="number"
        id={field.name}
        name={field.name}
        value={value ?? ''}
        onChange={handleChange}
        disabled={readonly}
        placeholder={field.placeholder}
        className={inputClasses}
        min={min}
        max={max}
        step="any"
      />
    </FieldWrapper>
  )
}
