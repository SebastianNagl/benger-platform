/**
 * Alert Component
 *
 * Displays alerts and notifications
 */

import { cn } from '@/lib/utils'
import {
  CheckCircleIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline'
import React from 'react'

interface AlertProps {
  variant?: 'info' | 'success' | 'warning' | 'error'
  className?: string
  children: React.ReactNode
}

const variantStyles = {
  info: {
    container:
      'bg-zinc-50 dark:bg-zinc-800/50 border-zinc-200 dark:border-zinc-700',
    icon: InformationCircleIcon,
    iconColor: 'text-zinc-500 dark:text-zinc-400',
  },
  success: {
    container:
      'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-800',
    icon: CheckCircleIcon,
    iconColor: 'text-emerald-600 dark:text-emerald-400',
  },
  warning: {
    container:
      'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800',
    icon: ExclamationTriangleIcon,
    iconColor: 'text-amber-600 dark:text-amber-400',
  },
  error: {
    container:
      'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800',
    icon: XCircleIcon,
    iconColor: 'text-red-600 dark:text-red-400',
  },
}

export function Alert({ variant = 'info', className, children }: AlertProps) {
  const styles = variantStyles[variant]
  const Icon = styles.icon

  return (
    <div className={cn('rounded-lg border p-4', styles.container, className)}>
      <div className="flex items-start gap-3">
        <Icon className={cn('mt-0.5 h-5 w-5 shrink-0', styles.iconColor)} />
        <div className="flex-1">{children}</div>
      </div>
    </div>
  )
}
