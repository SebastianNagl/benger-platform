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
        className={clsx('ui-input', className)}
        {...props}
      />
    )
  },
)

Input.displayName = 'Input'
