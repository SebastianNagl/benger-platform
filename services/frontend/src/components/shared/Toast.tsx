'use client'

import { AnimatePresence, motion } from 'framer-motion'
import React, { createContext, useCallback, useContext, useState } from 'react'
import { useI18n } from '@/contexts/I18nContext'

interface Toast {
  id: string
  message: string
  type: 'success' | 'error' | 'info' | 'warning'
  duration?: number
}

interface ToastContextType {
  addToast: (message: string, type?: Toast['type'], duration?: number) => string
  showToast: (
    message: string,
    type?: Toast['type'],
    duration?: number
  ) => string
  removeToast: (id: string) => void
}

const ToastContext = createContext<ToastContextType | undefined>(undefined)

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider')
  }
  return context
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const timeoutsRef = React.useRef<Map<string, NodeJS.Timeout>>(new Map())

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id))
    // Clear timeout if it exists
    const timeout = timeoutsRef.current.get(id)
    if (timeout) {
      clearTimeout(timeout)
      timeoutsRef.current.delete(id)
    }
  }, [])

  const addToast = useCallback(
    (message: string, type: Toast['type'] = 'info', duration = 4000) => {
      const id = Math.random().toString(36).substr(2, 9)
      const newToast: Toast = { id, message, type, duration }

      setToasts((prev) => {
        // Remove any existing toast with the same message (for loading toasts)
        const filtered = prev.filter((t) => t.message !== message)
        // Limit to max 5 toasts at once
        const newToasts = [...filtered, newToast]
        return newToasts.slice(-5)
      })

      if (duration > 0) {
        const timeout = setTimeout(() => {
          removeToast(id)
        }, duration)
        timeoutsRef.current.set(id, timeout)
      }

      // Return the ID so callers can track and remove it later
      return id
    },
    [removeToast]
  )

  // Cleanup timeouts on unmount
  React.useEffect(() => {
    const timeouts = timeoutsRef.current
    return () => {
      timeouts.forEach((timeout) => clearTimeout(timeout))
      timeouts.clear()
    }
  }, [])

  return (
    <ToastContext.Provider
      value={{ addToast, showToast: addToast, removeToast }}
    >
      {children}
      <ToastContainer toasts={toasts} onRemove={removeToast} />
    </ToastContext.Provider>
  )
}

function ToastContainer({
  toasts,
  onRemove,
}: {
  toasts: Toast[]
  onRemove: (id: string) => void
}) {
  return (
    <div className="pointer-events-none fixed right-4 top-4 z-50 max-w-sm space-y-2">
      <AnimatePresence mode="popLayout">
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} onRemove={onRemove} />
        ))}
      </AnimatePresence>
    </div>
  )
}

function ToastItem({
  toast,
  onRemove,
}: {
  toast: Toast
  onRemove: (id: string) => void
}) {
  const { t } = useI18n()

  const getToastStyles = (type: Toast['type']) => {
    switch (type) {
      case 'success':
        return 'bg-emerald-50 dark:bg-emerald-900/50 border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-200'
      case 'error':
        return 'bg-red-50 dark:bg-red-900/50 border-red-200 dark:border-red-800 text-red-800 dark:text-red-200'
      case 'warning':
        return 'bg-amber-50 dark:bg-amber-900/50 border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-200'
      default:
        return 'bg-blue-50 dark:bg-blue-900/50 border-blue-200 dark:border-blue-800 text-blue-800 dark:text-blue-200'
    }
  }

  const getIcon = (type: Toast['type']) => {
    switch (type) {
      case 'success':
        return '✓'
      case 'error':
        return '✗'
      case 'warning':
        return '⚠'
      default:
        return 'ℹ'
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, x: 100, scale: 0.8 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      exit={{ opacity: 0, x: 100, scale: 0.8 }}
      className={`${getToastStyles(toast.type)} pointer-events-auto flex min-w-0 items-center space-x-3 rounded-lg border p-4 shadow-lg`}
    >
      <span className="flex-shrink-0 text-lg">{getIcon(toast.type)}</span>
      <p className="min-w-0 flex-1 text-sm font-medium">{toast.message}</p>
      <button
        onClick={() => onRemove(toast.id)}
        className="flex-shrink-0 text-current transition-opacity hover:opacity-70"
      >
        <span className="sr-only">{t('shared.toast.close')}</span>
        <svg
          className="h-4 w-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M6 18L18 6M6 6l12 12"
          />
        </svg>
      </button>
    </motion.div>
  )
}
