'use client'

import {
  OperationStatus,
  OperationToast,
  OperationType,
} from '@/components/shared/OperationToast'
import { useI18n } from '@/contexts/I18nContext'
import { useCallback, useState } from 'react'

export interface OperationToastData {
  id: string
  type: OperationType
  status: OperationStatus
  taskId: string
  message: string
  details?: string
  persistent?: boolean
  createdAt: Date
}

export function useOperationToasts() {
  const { t } = useI18n()
  const [toasts, setToasts] = useState<OperationToastData[]>([])

  const addOperationToast = useCallback(
    (
      type: OperationType,
      status: OperationStatus,
      taskId: string,
      message: string,
      details?: string,
      persistent: boolean = false
    ) => {
      const id = `${type}-${taskId}-${Date.now()}`

      const newToast: OperationToastData = {
        id,
        type,
        status,
        taskId,
        message,
        details,
        persistent,
        createdAt: new Date(),
      }

      setToasts((prev) => {
        // Remove any existing toast for the same operation type and task
        const filtered = prev.filter(
          (toast) => !(toast.type === type && toast.taskId === taskId)
        )
        return [...filtered, newToast]
      })

      // Auto-dismiss non-persistent toasts after delay
      // Don't auto-dismiss 'started' status - let it transition to 'running' first
      if (!persistent && status !== 'running' && status !== 'started') {
        const dismissDelay = status === 'failed' ? 8000 : 5000
        setTimeout(() => {
          setToasts((prev) => prev.filter((toast) => toast.id !== id))
        }, dismissDelay)
      }

      return id
    },
    []
  )

  const updateOperationToast = useCallback(
    (
      type: OperationType,
      taskId: string,
      status: OperationStatus,
      message: string,
      details?: string
    ) => {
      setToasts((prev) =>
        prev.map((toast) => {
          if (toast.type === type && toast.taskId === taskId) {
            const updated = {
              ...toast,
              status,
              message,
              details,
            }

            // Auto-dismiss if operation completed and not persistent
            if (
              !toast.persistent &&
              (status === 'completed' || status === 'failed')
            ) {
              const dismissDelay = status === 'failed' ? 8000 : 5000
              setTimeout(() => {
                setToasts((current) => current.filter((t) => t.id !== toast.id))
              }, dismissDelay)
            }

            return updated
          }
          return toast
        })
      )
    },
    []
  )

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id))
  }, [])

  const dismissOperationToasts = useCallback(
    (type: OperationType, taskId: string) => {
      setToasts((prev) =>
        prev.filter(
          (toast) => !(toast.type === type && toast.taskId === taskId)
        )
      )
    },
    []
  )

  const clearAllToasts = useCallback(() => {
    setToasts([])
  }, [])

  const renderToasts = useCallback(() => {
    if (toasts.length === 0) {
      return null
    }

    return (
      <div className="fixed right-4 top-4 z-50 max-w-sm space-y-3">
        {toasts
          .sort((a, b) => a.createdAt.getTime() - b.createdAt.getTime()) // Oldest first (bottom to top stacking)
          .map((toast) => (
            <OperationToast
              key={toast.id}
              id={toast.id}
              type={toast.type}
              status={toast.status}
              taskId={toast.taskId}
              message={toast.message}
              details={toast.details}
              onDismiss={() => dismissToast(toast.id)}
            />
          ))}
      </div>
    )
  }, [toasts, dismissToast])

  // Helper functions for specific operation types
  const startGeneration = useCallback(
    (taskId: string, modelCount: number) => {
      return addOperationToast(
        'generation',
        'started',
        taskId,
        t('operations.generation.starting', { count: modelCount }),
        t('operations.generation.initializing'),
        false
      )
    },
    [addOperationToast]
  )

  const updateGeneration = useCallback(
    (
      taskId: string,
      status: OperationStatus,
      message: string,
      details?: string
    ) => {
      updateOperationToast('generation', taskId, status, message, details)
    },
    [updateOperationToast]
  )

  const startEvaluation = useCallback(
    (taskId: string, evaluationCount: number) => {
      return addOperationToast(
        'evaluation',
        'started',
        taskId,
        t('operations.evaluation.starting', { count: evaluationCount }),
        t('operations.evaluation.initializing'),
        false
      )
    },
    [addOperationToast]
  )

  const updateEvaluation = useCallback(
    (
      taskId: string,
      status: OperationStatus,
      message: string,
      details?: string
    ) => {
      updateOperationToast('evaluation', taskId, status, message, details)
    },
    [updateOperationToast]
  )

  return {
    toasts,
    addOperationToast,
    updateOperationToast,
    dismissToast,
    dismissOperationToasts,
    clearAllToasts,
    renderToasts,
    // Helper functions
    startGeneration,
    updateGeneration,
    startEvaluation,
    updateEvaluation,
  }
}
