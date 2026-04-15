import clsx from 'clsx'
import { ReactNode } from 'react'

interface BadgeProps {
  children: ReactNode
  variant?: 'default' | 'secondary' | 'destructive' | 'outline'
  className?: string
  onClick?: () => void
  'aria-label'?: string
}

export function Badge({
  children,
  variant = 'default',
  className,
  onClick,
  'aria-label': ariaLabel,
  ...props
}: BadgeProps) {
  const Component = onClick ? 'button' : 'span'
  const interactiveClasses = onClick
    ? 'cursor-pointer hover:opacity-80 transition-opacity focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-blue-500'
    : ''

  return (
    <Component
      onClick={onClick}
      aria-label={ariaLabel}
      className={clsx(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
        {
          'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-400':
            variant === 'default',
          'bg-zinc-100 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-300':
            variant === 'secondary',
          'bg-red-100 text-red-800 dark:bg-red-900/20 dark:text-red-400':
            variant === 'destructive',
          'border border-zinc-200 text-zinc-600 dark:border-zinc-700 dark:text-zinc-400':
            variant === 'outline',
        },
        interactiveClasses,
        className
      )}
      {...props}
    >
      {children}
    </Component>
  )
}
