import clsx from 'clsx'
import { InputHTMLAttributes, WheelEvent, forwardRef } from 'react'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  className?: string
}

// Scrolling over a focused number input must scroll the page, never change
// the value. React wheel listeners are passive, so preventDefault is not an
// option — blurring hands the wheel event back to page scroll.
const blurOnWheel = (e: WheelEvent<HTMLInputElement>) => e.currentTarget.blur()

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, onWheel, ...props }, ref) => {
    return (
      <input
        ref={ref}
        type={type}
        onWheel={onWheel ?? (type === 'number' ? blurOnWheel : undefined)}
        className={clsx(
          'block w-full rounded-md border-zinc-300 bg-white px-3 py-2 text-zinc-900 shadow-sm focus:border-emerald-500 focus:ring-emerald-500 dark:border-zinc-700 dark:bg-zinc-800 dark:text-white sm:text-sm',
          'disabled:cursor-not-allowed disabled:bg-zinc-50 disabled:text-zinc-500 dark:disabled:bg-zinc-900',
          className
        )}
        {...props}
      />
    )
  }
)

Input.displayName = 'Input'
