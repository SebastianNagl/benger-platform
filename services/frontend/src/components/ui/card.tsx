import { cn } from '@/lib/utils'
import React from 'react'

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode
}

export function Card({ className, children, ...props }: CardProps) {
  return (
    <div
      className={cn(
        'rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-900',
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
}

export function CardHeader({ className, children, ...props }: CardProps) {
  return (
    <div
      className={cn(
        'border-b border-zinc-200 px-6 py-4 dark:border-zinc-800',
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
}

export function CardTitle({ className, children, ...props }: CardProps) {
  return (
    <h3
      className={cn(
        'text-lg font-semibold text-zinc-900 dark:text-zinc-100',
        className
      )}
      {...props}
    >
      {children}
    </h3>
  )
}

export function CardDescription({ className, children, ...props }: CardProps) {
  return (
    <p
      className={cn('text-sm text-zinc-600 dark:text-zinc-400', className)}
      {...props}
    >
      {children}
    </p>
  )
}

export function CardContent({ className, children, ...props }: CardProps) {
  return (
    <div className={cn('px-6 py-4', className)} {...props}>
      {children}
    </div>
  )
}

export function CardFooter({ className, children, ...props }: CardProps) {
  return (
    <div
      className={cn(
        'border-t border-zinc-200 px-6 py-4 dark:border-zinc-800',
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
}
