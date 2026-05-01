'use client'

import { AnimatePresence, motion } from 'framer-motion'
import React, { createContext, useCallback, useContext, useEffect, useRef } from 'react'
import { useI18n } from '@/contexts/I18nContext'
import {
  DEFAULT_TOAST_DURATION_MS,
  ToastItem,
  ToastType,
  useNotificationStore,
} from '@/stores/notificationStore'

// Re-export the type for callers historically importing it from here.
export type Toast = ToastItem

interface ToastContextType {
  addToast: (
    message: string,
    type?: ToastType,
    duration?: number
  ) => string
  showToast: (
    message: string,
    type?: ToastType,
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

// Module-level dispatcher so non-component code (Zustand stores, effects
// running outside the React tree) can fire toasts. `<ToastProvider>` registers
// the dispatcher on mount; calls before mount log a warning and no-op.
let dispatcher: ToastContextType['addToast'] | null = null

export function setToastDispatcher(
  fn: ToastContextType['addToast'] | null
) {
  dispatcher = fn
}

export function toast(
  message: string,
  type?: ToastType,
  duration?: number
): string {
  if (!dispatcher) {
    if (typeof console !== 'undefined') {
      console.warn(
        'Toast dispatched before ToastProvider mounted:',
        message
      )
    }
    return ''
  }
  return dispatcher(message, type, duration)
}

const VALID_TOAST_TYPES: readonly ToastType[] = [
  'success',
  'error',
  'warning',
  'info',
]

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const toasts = useNotificationStore((s) => s.toasts)
  const storeAdd = useNotificationStore((s) => s.addToast)
  const storeRemove = useNotificationStore((s) => s.removeToast)
  const consumeFlashes = useNotificationStore((s) => s.consumeFlashes)
  const timeoutsRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(
    new Map()
  )

  // Wrap the store's addToast to also schedule the auto-dismiss timer.
  // The timer lives in the provider (not the store) so a rehydrated/persisted
  // toast can't keep ticking from a previous render's setTimeout — which
  // matters for tests and for the "live toasts don't persist" guarantee.
  const addToast = useCallback(
    (message: string, type?: ToastType, duration?: number) => {
      const effectiveDuration =
        duration === undefined ? DEFAULT_TOAST_DURATION_MS : duration
      const id = storeAdd(message, type, effectiveDuration)
      if (effectiveDuration > 0 && id) {
        const t = setTimeout(() => {
          storeRemove(id)
          timeoutsRef.current.delete(id)
        }, effectiveDuration)
        timeoutsRef.current.set(id, t)
      }
      return id
    },
    [storeAdd, storeRemove]
  )

  const removeToast = useCallback(
    (id: string) => {
      storeRemove(id)
      const t = timeoutsRef.current.get(id)
      if (t) {
        clearTimeout(t)
        timeoutsRef.current.delete(id)
      }
    },
    [storeRemove]
  )

  // Mount: register the module dispatcher and drain any pending flashes
  // (sessionStorage for same-origin reload, URL params for cross-origin
  // redirects). Strip the URL params after dispatch so they don't linger.
  useEffect(() => {
    setToastDispatcher(addToast)

    // Rehydrate live toasts from sessionStorage: for each persisted toast,
    // compute remaining = duration - elapsed-since-createdAt. Evict if the
    // window has already closed; re-arm a setTimeout for the remainder
    // otherwise. Persistent toasts (duration <= 0) stay forever.
    const now = Date.now()
    const rehydratedToasts = useNotificationStore.getState().toasts
    const survivors: typeof rehydratedToasts = []
    for (const t of rehydratedToasts) {
      const dur = t.duration ?? DEFAULT_TOAST_DURATION_MS
      if (dur <= 0) {
        survivors.push(t)
        continue
      }
      const elapsed = now - (t.createdAt ?? now)
      const remaining = dur - elapsed
      if (remaining <= 0) continue
      survivors.push(t)
      const handle = setTimeout(() => {
        storeRemove(t.id)
        timeoutsRef.current.delete(t.id)
      }, remaining)
      timeoutsRef.current.set(t.id, handle)
    }
    if (survivors.length !== rehydratedToasts.length) {
      useNotificationStore.setState({ toasts: survivors })
    }

    const flashes = consumeFlashes()
    for (const f of flashes) {
      addToast(f.message, f.type, f.duration)
    }

    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search)
      const flashMsg = params.get('flash_msg')
      if (flashMsg) {
        const flashTypeRaw = params.get('flash_type') as ToastType | null
        const flashDurationRaw = params.get('flash_duration')
        const type =
          flashTypeRaw && VALID_TOAST_TYPES.includes(flashTypeRaw)
            ? flashTypeRaw
            : 'info'
        const duration =
          flashDurationRaw !== null && !Number.isNaN(Number(flashDurationRaw))
            ? Number(flashDurationRaw)
            : undefined
        addToast(flashMsg, type, duration)
        params.delete('flash_msg')
        params.delete('flash_type')
        params.delete('flash_duration')
        const newSearch = params.toString()
        const newUrl =
          window.location.pathname +
          (newSearch ? `?${newSearch}` : '') +
          window.location.hash
        window.history.replaceState({}, '', newUrl)
      }
    }

    const timeouts = timeoutsRef.current
    return () => {
      setToastDispatcher(null)
      timeouts.forEach((t) => clearTimeout(t))
      timeouts.clear()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
  toasts: ToastItem[]
  onRemove: (id: string) => void
}) {
  return (
    <div
      className="pointer-events-none fixed right-4 top-4 z-50 max-w-sm space-y-2"
      data-testid="toast-container"
    >
      <AnimatePresence mode="popLayout">
        {toasts.map((toast) => (
          <ToastItemView key={toast.id} toast={toast} onRemove={onRemove} />
        ))}
      </AnimatePresence>
    </div>
  )
}

function ToastItemView({
  toast,
  onRemove,
}: {
  toast: ToastItem
  onRemove: (id: string) => void
}) {
  const { t } = useI18n()

  const getToastStyles = (type: ToastType) => {
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

  const getIcon = (type: ToastType) => {
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
      role={toast.type === 'error' ? 'alert' : 'status'}
      data-testid="toast-item"
      data-toast-type={toast.type}
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
