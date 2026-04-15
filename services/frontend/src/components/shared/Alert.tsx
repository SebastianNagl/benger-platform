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
      'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800',
    icon: InformationCircleIcon,
    iconColor: 'text-blue-600 dark:text-blue-400',
  },
  success: {
    container:
      'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800',
    icon: CheckCircleIcon,
    iconColor: 'text-green-600 dark:text-green-400',
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
        <Icon
          className={cn('mt-0.5 h-5 w-5 flex-shrink-0', styles.iconColor)}
        />
        <div className="flex-1">{children}</div>
      </div>
    </div>
  )
}
