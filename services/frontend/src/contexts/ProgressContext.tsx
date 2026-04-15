/**
 * Progress Context
 *
 * Global context for managing progress indicators for long-running operations
 */

'use client'

import { ProgressIndicator } from '@/components/shared/ProgressIndicator'
import { useI18n } from '@/contexts/I18nContext'
import { XMarkIcon } from '@heroicons/react/24/outline'
import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useState,
} from 'react'

interface ProgressItem {
  id: string
  label: string
  sublabel?: string
  progress: number
  status: 'idle' | 'running' | 'success' | 'error'
  indeterminate?: boolean
  onCancel?: () => void
}

interface ProgressContextType {
  progressItems: ProgressItem[]
  startProgress: (
    id: string,
    label: string,
    options?: {
      sublabel?: string
      indeterminate?: boolean
      onCancel?: () => void
    }
  ) => void
  updateProgress: (id: string, progress: number, sublabel?: string) => void
  completeProgress: (id: string, status?: 'success' | 'error') => void
  removeProgress: (id: string) => void
}

const ProgressContext = createContext<ProgressContextType | undefined>(
  undefined
)

export function ProgressProvider({ children }: { children: ReactNode }) {
  const { t } = useI18n()
  const [progressItems, setProgressItems] = useState<ProgressItem[]>([])

  const startProgress = useCallback(
    (
      id: string,
      label: string,
      options?: {
        sublabel?: string
        indeterminate?: boolean
        onCancel?: () => void
      }
    ) => {
      setProgressItems((prev) => {
        // Remove existing item with same id
        const filtered = prev.filter((item) => item.id !== id)
        return [
          ...filtered,
          {
            id,
            label,
            sublabel: options?.sublabel,
            progress: 0,
            status: 'running',
            indeterminate: options?.indeterminate,
            onCancel: options?.onCancel,
          },
        ]
      })
    },
    []
  )

  const updateProgress = useCallback(
    (id: string, progress: number, sublabel?: string) => {
      setProgressItems((prev) =>
        prev.map((item) =>
          item.id === id
            ? {
                ...item,
                progress: Math.max(0, Math.min(100, progress)),
                sublabel: sublabel !== undefined ? sublabel : item.sublabel,
              }
            : item
        )
      )
    },
    []
  )

  const removeProgress = useCallback((id: string) => {
    setProgressItems((prev) => prev.filter((item) => item.id !== id))
  }, [])

  const completeProgress = useCallback(
    (id: string, status: 'success' | 'error' = 'success') => {
      setProgressItems((prev) =>
        prev.map((item) =>
          item.id === id ? { ...item, progress: 100, status } : item
        )
      )

      // Auto-remove success items after delay
      if (status === 'success') {
        setTimeout(() => {
          removeProgress(id)
        }, 3000)
      }
    },
    [removeProgress]
  )

  return (
    <ProgressContext.Provider
      value={{
        progressItems,
        startProgress,
        updateProgress,
        completeProgress,
        removeProgress,
      }}
    >
      {children}

      {/* Progress Overlay */}
      {progressItems.length > 0 && (
        <div className="fixed bottom-4 right-4 z-50 w-full max-w-md space-y-3 px-4">
          {progressItems.map((item) => (
            <div
              key={item.id}
              className="animate-slide-up rounded-lg border border-zinc-200 bg-white p-4 shadow-lg dark:border-zinc-700 dark:bg-zinc-900"
            >
              <div className="mb-2 flex items-start justify-between">
                <div className="flex-1">
                  <ProgressIndicator
                    progress={item.progress}
                    label={item.label}
                    sublabel={item.sublabel}
                    status={item.status}
                    indeterminate={item.indeterminate}
                    showPercentage={!item.indeterminate}
                  />
                </div>
                <div className="ml-4 flex items-center gap-1">
                  {item.onCancel && item.status === 'running' && (
                    <button
                      onClick={item.onCancel}
                      className="rounded p-1 transition-colors hover:bg-zinc-100 dark:hover:bg-zinc-800"
                      title={t('progress.cancel')}
                    >
                      <XMarkIcon className="h-4 w-4" />
                    </button>
                  )}
                  {(item.status === 'error' || item.status === 'success') && (
                    <button
                      onClick={() => removeProgress(item.id)}
                      className="rounded p-1 transition-colors hover:bg-zinc-100 dark:hover:bg-zinc-800"
                      title={t('progress.dismiss')}
                    >
                      <XMarkIcon className="h-4 w-4" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </ProgressContext.Provider>
  )
}

export function useProgress() {
  const context = useContext(ProgressContext)
  if (!context) {
    throw new Error('useProgress must be used within a ProgressProvider')
  }
  return context
}

// Animation styles
const style = `
@keyframes slide-up {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.animate-slide-up {
  animation: slide-up 0.3s ease-out;
}
`

if (typeof document !== 'undefined') {
  const styleElement = document.createElement('style')
  styleElement.textContent = style
  document.head.appendChild(styleElement)
}
