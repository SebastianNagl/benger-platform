/**
 * LikertInput Component
 *
 * 7-point Likert scale for annotation questionnaires.
 * Wraps the shared LikertScale component for use within Label Studio XML configs.
 */

import { LikertScale } from '@/components/shared/LikertScale'
import { buildAnnotationResult } from '@/lib/labelConfig/dataBinding'
import { AnnotationComponentProps } from '@/lib/labelConfig/registry'
import { useState } from 'react'

export default function LikertInput({
  config,
  value: externalValue,
  onChange,
  onAnnotation,
}: AnnotationComponentProps) {
  const [value, setValue] = useState<number | undefined>(externalValue || undefined)

  const name = config.props.name || config.name || 'likert'
  const toName = config.props.toName
  const min = parseInt(config.props.min || '1')
  const max = parseInt(config.props.max || '7')
  const required = config.props.required === 'true'
  const label = config.props.label || name

  const handleChange = (newValue: number) => {
    setValue(newValue)
    onChange(newValue)

    if (toName) {
      const result = buildAnnotationResult(name, 'Likert', newValue, toName)
      onAnnotation(result)
    }
  }

  return (
    <div className="likert-input">
      <LikertScale
        name={name}
        label={label}
        value={value}
        onChange={handleChange}
        required={required}
        min={min}
        max={max}
      />
      {config.props.hint && (
        <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
          {config.props.hint}
        </p>
      )}
    </div>
  )
}
