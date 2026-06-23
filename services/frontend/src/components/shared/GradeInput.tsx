'use client'

import { useEffect, useState } from 'react'

export interface GradeInputProps {
  id: string
  name: string
  value: number | undefined
  onChange: (value: number | undefined) => void
  className: string
  placeholder?: string
}

// Grade input component that accepts comma/dot and displays with comma
export function GradeInput({
  id,
  name,
  value,
  onChange,
  className,
  placeholder = '0,00 - 18,00',
}: GradeInputProps) {
  const [rawValue, setRawValue] = useState(() =>
    value != null ? String(value).replace('.', ',') : ''
  )

  // Sync from external value changes (e.g. profile load)
  useEffect(() => {
    const formatted = value != null ? String(value).replace('.', ',') : ''
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setRawValue((prev) => {
      // Only update if the numeric value actually changed
      const prevNum = prev ? parseFloat(prev.replace(',', '.')) : undefined
      if (prevNum === value) return prev
      return formatted
    })
  }, [value])

  return (
    <input
      type="text"
      inputMode="decimal"
      id={id}
      name={name}
      placeholder={placeholder}
      value={rawValue}
      onChange={(e) => {
        const input = e.target.value
        // Allow digits, comma, dot, and empty
        if (input && !/^[\d.,]*$/.test(input)) return
        setRawValue(input)
        // Parse and propagate numeric value
        if (!input) {
          onChange(undefined)
        } else {
          const parsed = parseFloat(input.replace(',', '.'))
          if (!isNaN(parsed)) onChange(parsed)
        }
      }}
      onBlur={() => {
        // Format with comma on blur
        if (rawValue) {
          const parsed = parseFloat(rawValue.replace(',', '.'))
          if (!isNaN(parsed)) {
            setRawValue(String(parsed).replace('.', ','))
          }
        }
      }}
      className={className}
    />
  )
}

export default GradeInput
