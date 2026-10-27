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
          // Pill field like SearchInput and the Select trigger. A ring, not a
          // border: Tailwind's preflight zeroes border widths.
          'rounded-full px-4 py-2',
          'block w-full bg-white text-base text-zinc-900 ring-1 ring-zinc-900/10 transition placeholder:text-zinc-500 hover:ring-zinc-900/20 focus:ring-2 focus:ring-emerald-500 focus:outline-none sm:text-sm dark:bg-white/5 dark:text-white dark:ring-white/10 dark:ring-inset dark:placeholder:text-zinc-400 dark:hover:ring-white/20 dark:focus:ring-emerald-400',
          'disabled:cursor-not-allowed disabled:bg-zinc-50 disabled:text-zinc-500 disabled:hover:ring-zinc-900/10 dark:disabled:bg-white/2.5',
          className,
        )}
        {...props}
      />
    )
  },
)

Input.displayName = 'Input'
