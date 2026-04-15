/**
 * Table Checkbox Component
 * A checkbox specifically designed for table selection with indeterminate state support
 */

import { useEffect, useRef } from 'react'

interface TableCheckboxProps {
  checked: boolean
  indeterminate?: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
  className?: string
  'data-testid'?: string
}

export function TableCheckbox({
  checked,
  indeterminate = false,
  onChange,
  disabled = false,
  className = '',
  'data-testid': dataTestId,
}: TableCheckboxProps) {
  const checkboxRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (checkboxRef.current) {
      checkboxRef.current.indeterminate = indeterminate
    }
  }, [indeterminate])

  return (
    <input
      ref={checkboxRef}
      type="checkbox"
      checked={checked}
      onChange={(e) => onChange(e.target.checked)}
      disabled={disabled}
      className={`h-4 w-4 rounded border-zinc-300 text-emerald-600 accent-emerald-600 transition-colors focus:ring-2 focus:ring-emerald-500 focus:ring-offset-0 focus:ring-offset-white disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-600 dark:text-emerald-500 dark:accent-emerald-500 dark:focus:ring-offset-zinc-900 ${indeterminate ? 'bg-emerald-600 dark:bg-emerald-500' : ''} ${className} `}
      style={{
        cursor: disabled ? 'not-allowed' : 'pointer',
        accentColor: indeterminate ? '#10b981' : undefined,
      }}
      data-testid={dataTestId}
    />
  )
}
