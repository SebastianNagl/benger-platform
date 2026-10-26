/**
 * Checkbox component - Reusable checkbox input
 */

import { cn } from '@/lib/utils'
import { forwardRef, InputHTMLAttributes } from 'react'

export interface CheckboxProps extends Omit<
  InputHTMLAttributes<HTMLInputElement>,
  'type'
> {
  label?: string
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(
  ({ className, label, ...props }, ref) => {
    return (
      <div className="flex items-center">
        <input
          type="checkbox"
          ref={ref}
          className={cn(
            'h-4 w-4 rounded border-zinc-300 text-emerald-600',
            'focus:ring-2 focus:ring-emerald-500 focus:ring-offset-0',
            'disabled:cursor-not-allowed disabled:opacity-50',
            className,
          )}
          {...props}
        />
        {label && (
          <label htmlFor={props.id} className="ml-2 text-sm text-zinc-700">
            {label}
          </label>
        )}
      </div>
    )
  },
)

Checkbox.displayName = 'Checkbox'
