import clsx from 'clsx'
import { ReactNode } from 'react'

interface LabelProps {
  htmlFor?: string
  children: ReactNode
  className?: string
}

export function Label({ htmlFor, children, className }: LabelProps) {
  return (
    <label
      htmlFor={htmlFor}
      className={clsx(
        'mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300',
        className
      )}
    >
      {children}
    </label>
  )
}
