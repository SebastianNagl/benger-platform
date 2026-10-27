/**
 * TextArea Field Component
 *
 * Multi-line text input field for the template system.
 *
 * Issue #216: Implement Unified Task Configuration and Display System
 */

import React from 'react'
import { BaseFieldProps, FieldWrapper, getInputClasses } from './BaseField'

export function TextAreaField({
  field,
  value,
  onChange,
  readonly = false,
  errors = [],
  context,
  className = '',
}: BaseFieldProps) {
  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    onChange(e.target.value)
  }

  const hasError = errors.length > 0
  const inputClasses = getInputClasses(hasError, readonly, true)

  // Calculate rows based on context
  const rows = context === 'annotation' ? 6 : 4

  return (
    <FieldWrapper field={field} errors={errors} className={className}>
      <textarea
        id={field.name}
        name={field.name}
        value={value || ''}
        onChange={handleChange}
        disabled={readonly}
        placeholder={field.placeholder}
        className={`${inputClasses} resize-y`}
        rows={rows}
        maxLength={field.validation?.find((v) => v.type === 'maxLength')?.value}
      />
      {field.validation?.find((v) => v.type === 'maxLength') && (
        <div className="mt-1 text-right text-xs text-zinc-500 dark:text-zinc-400">
          {value?.length || 0} /{' '}
          {field.validation.find((v) => v.type === 'maxLength')?.value}
        </div>
      )}
    </FieldWrapper>
  )
}
