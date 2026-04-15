/**
 * URL Field Component
 *
 * URL input field with validation for the template system.
 *
 * Issue #216: Implement Unified Task Configuration and Display System
 */

import { useI18n } from '@/contexts/I18nContext'
import React from 'react'
import { BaseFieldProps, FieldWrapper, getInputClasses } from './BaseField'

export function UrlField({
  field,
  value,
  onChange,
  readonly = false,
  errors = [],
  context,
  className = '',
}: BaseFieldProps) {
  const { t } = useI18n()
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange(e.target.value)
  }

  const hasError = errors.length > 0
  const inputClasses = getInputClasses(hasError, readonly)

  return (
    <FieldWrapper field={field} errors={errors} className={className}>
      <input
        type="url"
        id={field.name}
        name={field.name}
        value={value || ''}
        onChange={handleChange}
        disabled={readonly}
        placeholder={field.placeholder || t('fields.urlPlaceholder')}
        className={inputClasses}
      />
    </FieldWrapper>
  )
}
