import { cn } from '@/lib/utils'
import { HTMLAttributes, ReactNode } from 'react'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
  className?: string
  onClick?: () => void
}

export function Card({ children, className, onClick, ...props }: CardProps) {
  return (
    <div
      className={cn(
        'rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-900',
        className,
      )}
      onClick={onClick}
      {...props}
    >
      {children}
    </div>
  )
}

interface CardSectionProps extends HTMLAttributes<HTMLElement> {
  children: ReactNode
}

export function CardHeader({
  className,
  children,
  ...props
}: CardSectionProps) {
  return (
    <div
      className={cn(
        'border-b border-zinc-200 px-6 py-4 dark:border-zinc-800',
        className,
      )}
      {...props}
    >
      {children}
    </div>
  )
}

export function CardTitle({ className, children, ...props }: CardSectionProps) {
  return (
    <h3
      className={cn(
        'text-lg font-semibold text-zinc-900 dark:text-zinc-100',
        className,
      )}
      {...props}
    >
      {children}
    </h3>
  )
}

export function CardDescription({
  className,
  children,
  ...props
}: CardSectionProps) {
  return (
    <p
      className={cn('text-sm text-zinc-600 dark:text-zinc-400', className)}
      {...props}
    >
      {children}
    </p>
  )
}

export function CardContent({
  className,
  children,
  ...props
}: CardSectionProps) {
  return (
    <div className={cn('px-6 py-4', className)} {...props}>
      {children}
    </div>
  )
}

export function CardFooter({
  className,
  children,
  ...props
}: CardSectionProps) {
  return (
    <div
      className={cn(
        'border-t border-zinc-200 px-6 py-4 dark:border-zinc-800',
        className,
      )}
      {...props}
    >
      {children}
    </div>
  )
}
