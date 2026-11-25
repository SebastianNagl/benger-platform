/**
 * TextAreaInput Component
 *
 * Text input for annotations, linked to object tags via toName
 *
 * @param hideSubmitButton - When true, hides the individual submit button to prevent
 *                          duplicate submissions when used within larger interfaces like
 *                          DynamicAnnotationInterface. Defaults to false for backward compatibility.
 */

import { Label } from '@/components/shared/Label'
import { Textarea } from '@/components/shared/Textarea'
import { useI18n } from '@/contexts/I18nContext'
import { buildAnnotationResult } from '@/lib/labelConfig/dataBinding'
import { AnnotationComponentProps } from '@/lib/labelConfig/registry'
import { logger } from '@/lib/utils/logger'
import React, { useEffect, useState } from 'react'

export default function TextAreaInput({
  config,
  taskData,
  value: externalValue,
  onChange,
  onAnnotation,
  hideSubmitButton = false,
  readOnly = false,
}: AnnotationComponentProps) {
  const { t } = useI18n()
  const [value, setValue] = useState(externalValue || '')

  // Get configuration
  const name = config.props.name || config.name || 'textarea'
  const toName = config.props.toName
  const placeholder =
    config.props.placeholder || t('annotation.textAreaPlaceholder')
  const rows = parseInt(config.props.rows || '4')
  const maxSubmissions = parseInt(config.props.maxSubmissions || '1')
  const required = config.props.required === 'true'
  const showSubmitButton = config.props.showSubmitButton !== 'false'

  // Take a value from outside (initial values, a cleared form, a restored
  // draft; undefined clears the field) when it changes, during render. The
  // form hands every typed value straight back as externalValue; setting it
  // again from an effect scheduled one more update per key, and after about
  // fifty keys typed without a pause React stopped with "Maximum update depth
  // exceeded" and dropped that key.
  const [syncedValue, setSyncedValue] = useState(externalValue)
  if (externalValue !== syncedValue) {
    setSyncedValue(externalValue)
    if ((externalValue || '') !== value) setValue(externalValue || '')
  }

  // Create annotation after a delay when value changes (debounced)
  useEffect(() => {
    if (toName && value && value.length > 0) {
      const timer = setTimeout(() => {
        const result = buildAnnotationResult(name, 'TextArea', value, toName)
        logger.debug('Auto-creating annotation after delay:', result)
        onAnnotation(result)
      }, 500) // Wait 500ms after user stops typing

      return () => clearTimeout(timer)
    }
  }, [value, name, toName, onAnnotation])

  // Handle value change
  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    if (readOnly) return
    const newValue = e.target.value
    setValue(newValue)
    onChange(newValue)

    // Only create annotation result on blur or submit, not on every keystroke
    // This prevents potential stack overflow from too many updates
  }

  // Handle blur event to create annotation
  const handleBlur = () => {
    logger.debug('TextAreaInput handleBlur called', { name, value, toName })
    if (toName && value) {
      const result = buildAnnotationResult(name, 'TextArea', value, toName)
      logger.debug('Creating annotation result:', result)
      onAnnotation(result)
    }
  }

  // Handle submit (if submit button is shown)
  const handleSubmit = () => {
    if (!value.trim() && required) {
      return
    }

    if (toName) {
      const result = buildAnnotationResult(name, 'TextArea', value, toName)
      onAnnotation(result)
    }
  }

  return (
    <div className="textarea-input space-y-2">
      <Label htmlFor={name}>
        {config.props.label || name}
        {required && <span className="ml-1 text-red-500">*</span>}
      </Label>

      <Textarea
        id={name}
        name={name}
        value={value}
        onChange={handleChange}
        onBlur={handleBlur}
        placeholder={placeholder}
        rows={rows}
        required={required}
        readOnly={readOnly}
        aria-readonly={readOnly || undefined}
        className="w-full"
      />

      {showSubmitButton && !hideSubmitButton && !readOnly && (
        <button
          type="button"
          onClick={handleSubmit}
          disabled={required && !value.trim()}
          className="h-8 rounded-full bg-zinc-900 px-3 text-sm text-white hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-emerald-500 dark:hover:bg-emerald-400"
        >
          {t('common.submit')}
        </button>
      )}

      {config.props.hint && (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          {config.props.hint}
        </p>
      )}
    </div>
  )
}
