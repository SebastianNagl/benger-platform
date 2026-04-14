/**
 * NumberInput Component
 *
 * Numeric input for annotations
 */

import { Input } from '@/components/shared/Input'
import { Label } from '@/components/shared/Label'
import { useI18n } from '@/contexts/I18nContext'
import { buildAnnotationResult } from '@/lib/labelConfig/dataBinding'
import { AnnotationComponentProps } from '@/lib/labelConfig/registry'
import React, { useState } from 'react'

export default function NumberInput({
  config,
  taskData,
  value: externalValue,
  onChange,
  onAnnotation,
}: AnnotationComponentProps) {
  const { t } = useI18n()
  const [value, setValue] = useState<string>(externalValue?.toString() || '')

  // Get configuration
  const name = config.props.name || config.name || 'number'
  const toName = config.props.toName
  const min = config.props.min
  const max = config.props.max
  const step = config.props.step || '1'
  const required = config.props.required === 'true'
  const placeholder = config.props.placeholder || t('annotation.numberPlaceholder')

  // Handle value change
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value
    setValue(newValue)

    const numericValue = parseFloat(newValue)
    if (!isNaN(numericValue)) {
      onChange(numericValue)

      // Create annotation result
      if (toName) {
        const result = buildAnnotationResult(
          name,
          'Number',
          numericValue,
          toName
        )
        onAnnotation(result)
      }
    }
  }

  return (
    <div className="number-input space-y-2">
      <Label htmlFor={name}>
        {config.props.label || name}
        {required && <span className="ml-1 text-red-500">*</span>}
      </Label>

      <Input
        id={name}
        type="number"
        value={value}
        onChange={handleChange}
        placeholder={placeholder}
        min={min}
        max={max}
        step={step}
        required={required}
        className="w-full"
      />

      {config.props.hint && (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          {config.props.hint}
        </p>
      )}
    </div>
  )
}
