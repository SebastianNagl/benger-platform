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
import { logger } from '@/lib/utils/logger'
import { Textarea } from '@/components/shared/Textarea'
import { buildAnnotationResult } from '@/lib/labelConfig/dataBinding'
import { AnnotationComponentProps } from '@/lib/labelConfig/registry'
import React, { useEffect, useState } from 'react'

export default function TextAreaInput({
  config,
  taskData,
  value: externalValue,
  onChange,
  onAnnotation,
  hideSubmitButton = false,
}: AnnotationComponentProps) {
  const [value, setValue] = useState(externalValue || '')

  // Get configuration
  const name = config.props.name || config.name || 'textarea'
  const toName = config.props.toName
  const placeholder = config.props.placeholder || 'Enter your annotation...'
  const rows = parseInt(config.props.rows || '4')
  const maxSubmissions = parseInt(config.props.maxSubmissions || '1')
  const required = config.props.required === 'true'
  const showSubmitButton = config.props.showSubmitButton !== 'false'

  // Sync external value changes - properly handle undefined to clear the field
  useEffect(() => {
    // When externalValue is undefined or empty string, clear the field
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Intentional: sync with external prop
    setValue(externalValue || '')
  }, [externalValue])

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
        className="w-full"
      />

      {showSubmitButton && !hideSubmitButton && (
        <button
          type="button"
          onClick={handleSubmit}
          disabled={required && !value.trim()}
          className="rounded-md bg-emerald-600 px-3 py-1 text-sm text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Submit
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
