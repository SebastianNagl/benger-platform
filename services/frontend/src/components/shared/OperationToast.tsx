'use client'

import { useI18n } from '@/contexts/I18nContext'
import { useRouter } from 'next/navigation'
// Using a simple X character instead of lucide-react icon

export type OperationStatus = 'started' | 'running' | 'completed' | 'failed'
export type OperationType = 'generation' | 'evaluation'

interface OperationToastProps {
  id: string
  type: OperationType
  status: OperationStatus
  taskId: string
  message: string
  details?: string
  onDismiss: () => void
  clickable?: boolean
}

export function OperationToast({
  id,
  type,
  status,
  taskId,
  message,
  details,
  onDismiss,
  clickable = true,
}: OperationToastProps) {
  const router = useRouter()
  const { t } = useI18n()

  const getStatusColor = () => {
    switch (status) {
      case 'started':
        return 'bg-emerald-500 border-emerald-600'
      case 'running':
        return 'bg-amber-500 border-amber-600'
      case 'completed':
        return 'bg-emerald-500 border-emerald-600'
      case 'failed':
        return 'bg-red-500 border-red-600'
      default:
        return 'bg-zinc-500 border-zinc-600'
    }
  }

  const getStatusIcon = () => {
    switch (status) {
      case 'started':
        return '▶'
      case 'running':
        return (
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"></div>
        )
      case 'completed':
        return '✓'
      case 'failed':
        return '✗'
      default:
        return '○'
    }
  }

  const getBackgroundColor = () => {
    switch (status) {
      case 'started':
        return 'bg-emerald-50 border-emerald-200 dark:bg-emerald-900/20 dark:border-emerald-700'
      case 'running':
        return 'bg-amber-50 border-amber-200 dark:bg-amber-900/20 dark:border-amber-700'
      case 'completed':
        return 'bg-emerald-50 border-emerald-200 dark:bg-emerald-900/20 dark:border-emerald-700'
      case 'failed':
        return 'bg-red-50 border-red-200 dark:bg-red-900/20 dark:border-red-700'
      default:
        return 'bg-zinc-50 border-zinc-200 dark:bg-zinc-900/20 dark:border-zinc-700'
    }
  }

  const getTextColor = () => {
    switch (status) {
      case 'started':
        return 'text-emerald-800 dark:text-emerald-200'
      case 'running':
        return 'text-amber-800 dark:text-amber-200'
      case 'completed':
        return 'text-emerald-800 dark:text-emerald-200'
      case 'failed':
        return 'text-red-800 dark:text-red-200'
      default:
        return 'text-zinc-800 dark:text-zinc-200'
    }
  }

  const handleClick = () => {
    // TODO: Update to use project-based routing
    // Navigation disabled - tasks are now accessed through projects
  }

  const typeLabel = type === 'generation' ? t('toasts.operation.generation') : t('toasts.operation.evaluation')

  return (
    <div
      className={`pointer-events-auto relative w-full max-w-sm rounded-lg border shadow-lg ${getBackgroundColor()} ${
        clickable &&
        (status === 'running' || status === 'completed' || status === 'failed')
          ? 'cursor-pointer transition-shadow duration-200 hover:shadow-xl'
          : ''
      } `}
      onClick={handleClick}
    >
      {/* Status indicator bar */}
      <div
        className={`absolute left-0 right-0 top-0 h-1 rounded-t-lg ${getStatusColor()}`}
      ></div>

      <div className="p-4">
        <div className="flex items-start">
          <div className="mr-3 mt-0.5 flex-shrink-0">
            <div
              className={`flex h-8 w-8 items-center justify-center rounded-full ${getStatusColor()}`}
            >
              <span className="text-sm text-white">{getStatusIcon()}</span>
            </div>
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between">
              <h3 className={`text-sm font-medium ${getTextColor()}`}>
                {typeLabel}
              </h3>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onDismiss()
                }}
                className={`ml-2 flex-shrink-0 rounded-full p-1 transition-colors hover:bg-black/10 ${getTextColor()}`}
              >
                <span className="text-lg leading-none">×</span>
              </button>
            </div>

            <p className={`mt-1 text-sm ${getTextColor()}`}>{message}</p>

            {details && (
              <p className={`mt-1 text-xs opacity-75 ${getTextColor()}`}>
                {details}
              </p>
            )}

            {clickable &&
              (status === 'running' ||
                status === 'completed' ||
                status === 'failed') && (
                <p className={`mt-2 text-xs opacity-60 ${getTextColor()}`}>
                  {t('toasts.operation.viewStatus')}
                </p>
              )}
          </div>
        </div>
      </div>
    </div>
  )
}
