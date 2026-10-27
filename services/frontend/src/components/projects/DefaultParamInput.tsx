import { Input } from '@/components/shared/Input'
import React from 'react'

interface DefaultParamInputProps {
  /** Current value; ``fallback`` is shown when it is undefined. */
  value: number | undefined
  fallback: number
  min: number
  max: number
  step: number
  placeholder: string
  disabled: boolean
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void
}

/**
 * The shared numeric default-parameter ``<input>`` used by EvaluationDefaultsCard
 * and GenerationDefaultsCard (temperature + max-tokens). Extracted to collapse the
 * byte-identical input + disabled-styling boilerplate that was duplicated across
 * both cards; the card-specific value/handlers are passed in as props.
 */
export function DefaultParamInput({
  value,
  fallback,
  min,
  max,
  step,
  placeholder,
  disabled,
  onChange,
}: DefaultParamInputProps) {
  return (
    <Input
      type="number"
      min={min}
      max={max}
      step={step}
      value={value ?? fallback}
      placeholder={placeholder}
      disabled={disabled}
      onChange={onChange}
      className="mt-1 h-8"
    />
  )
}

export default DefaultParamInput
