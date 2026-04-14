'use client'

import { useI18n } from '@/contexts/I18nContext'
import Link from 'next/link'
import React from 'react'
import { Button } from './Button'

interface EmptyStateProps {
  icon?: React.ReactNode
  title: string
  description: string
  action?: {
    label: string
    href?: string
    onClick?: () => void
  }
  className?: string
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className = '',
}: EmptyStateProps) {
  return (
    <div className={`px-4 py-12 text-center ${className}`}>
      {icon && (
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-zinc-100 dark:bg-zinc-800">
          {icon}
        </div>
      )}
      <h3 className="mb-2 text-lg font-medium text-zinc-900 dark:text-white">
        {title}
      </h3>
      <p className="mx-auto mb-6 max-w-md text-sm text-zinc-600 dark:text-zinc-400">
        {description}
      </p>
      {action &&
        (action.href ? (
          <Link href={action.href}>
            <Button variant="filled">{action.label}</Button>
          </Link>
        ) : (
          <Button variant="filled" onClick={action.onClick}>
            {action.label}
          </Button>
        ))}
    </div>
  )
}

// Specific empty state for missing analytics data
export function NoAnalyticsDataEmptyState({
  taskName,
  onRetry,
  onBackToDashboard,
}: {
  taskName?: string
  onRetry?: () => void
  onBackToDashboard?: () => void
}) {
  const { t } = useI18n()

  return (
    <EmptyState
      icon={
        <svg
          className="h-8 w-8 text-zinc-400 dark:text-zinc-500"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 00-2 2v6a2 2 0 00-2 2"
          />
        </svg>
      }
      title={t('emptyStates.noAnalytics')}
      description={
        taskName
          ? t('emptyStates.noAnalyticsMessageWithTask', { taskName })
          : t('emptyStates.noAnalyticsMessage')
      }
      action={
        onBackToDashboard
          ? {
              label: t('emptyStates.backToDashboard'),
              onClick: onBackToDashboard,
            }
          : undefined
      }
    />
  )
}

// Empty state for when no tasks are selected
export function NoTaskSelectedEmptyState({
  onSelectTask,
}: {
  onSelectTask?: () => void
}) {
  const { t } = useI18n()

  return (
    <EmptyState
      icon={
        <svg
          className="h-8 w-8 text-zinc-400 dark:text-zinc-500"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
          />
        </svg>
      }
      title={t('emptyStates.selectTask')}
      description={t('emptyStates.selectTaskMessage')}
      action={
        onSelectTask
          ? {
              label: t('emptyStates.browseTasks'),
              onClick: onSelectTask,
            }
          : undefined
      }
    />
  )
}
