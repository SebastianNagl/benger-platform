import clsx from 'clsx'
import { HTMLAttributes, ReactNode } from 'react'

interface BadgeProps extends Omit<
  HTMLAttributes<HTMLElement>,
  'onClick' | 'children' | 'className'
> {
  children: ReactNode
  variant?:
    | 'default'
    | 'secondary'
    | 'destructive'
    | 'outline'
    | 'success'
    | 'warning'
    | 'info'
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
    ? 'cursor-pointer hover:opacity-80 transition-opacity focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-emerald-500'
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
          'bg-emerald-100 text-emerald-800 ring-1 ring-emerald-600/20 ring-inset dark:bg-emerald-900/30 dark:text-emerald-300':
            variant === 'success',
          'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300':
            variant === 'warning',
          'bg-sky-100 text-sky-800 dark:bg-sky-900/30 dark:text-sky-300':
            variant === 'info',
        },
        interactiveClasses,
        className,
      )}
      {...props}
    >
      {children}
    </Component>
  )
}
