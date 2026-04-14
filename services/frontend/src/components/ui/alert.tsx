import { cn } from '@/lib/utils'
import React from 'react'

interface AlertProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'destructive'
  children: React.ReactNode
}

export function Alert({
  className,
  variant = 'default',
  children,
  ...props
}: AlertProps) {
  const variants = {
    default:
      'bg-blue-50 border-blue-200 text-blue-900 dark:bg-blue-900/20 dark:border-blue-800 dark:text-blue-200',
    destructive:
      'bg-red-50 border-red-200 text-red-900 dark:bg-red-900/20 dark:border-red-800 dark:text-red-200',
  }

  return (
    <div
      className={cn(
        'rounded-md border px-4 py-3',
        variants[variant],
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
}

export function AlertDescription({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p className={cn('text-sm', className)} {...props}>
      {children}
    </p>
  )
}
