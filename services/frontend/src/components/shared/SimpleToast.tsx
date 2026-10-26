'use client'

import React, { createContext, useCallback, useContext, useState } from 'react'

interface Toast {
  id: string
  message: string
  type: 'success' | 'error' | 'info' | 'warning'
  duration?: number
}

interface ToastContextType {
  addToast: (message: string, type?: Toast['type'], duration?: number) => void
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

export function SimpleToastProvider({
  children,
}: {
  children: React.ReactNode
}) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id))
  }, [])

  const addToast = useCallback(
    (message: string, type: Toast['type'] = 'info', duration = 5000) => {
      const id = Math.random().toString(36).substring(2, 9)
      const toast: Toast = { id, message, type, duration }

      setToasts((prev) => [...prev, toast])

      if (duration > 0) {
        setTimeout(() => removeToast(id), duration)
      }
    },
    [removeToast],
  )

  return (
    <ToastContext.Provider value={{ addToast, removeToast }}>
      {children}
      <div className="fixed top-4 right-4 z-50 space-y-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`max-w-sm rounded-lg p-4 text-white shadow-lg ${
              toast.type === 'success'
                ? 'bg-emerald-500'
                : toast.type === 'error'
                  ? 'bg-red-500'
                  : toast.type === 'warning'
                    ? 'bg-amber-500'
                    : 'bg-zinc-800 dark:bg-zinc-700'
            }`}
          >
            <div className="flex items-center justify-between">
              <span>{toast.message}</span>
              <button
                onClick={() => removeToast(toast.id)}
                className="ml-4 text-white hover:text-zinc-200"
              >
                ×
              </button>
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
