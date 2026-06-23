/**
 * Progress Context
 *
 * Public API for showing progress toasts. Backed by the same notification
 * store + ToastProvider as regular toasts so progress + completion + error
 * messages all render through one component, in one screen position, with
 * one set of styles. There is no second overlay.
 *
 * Lifecycle:
 *   startProgress(id, label, options?)   -> persistent toast with progress bar
 *   updateProgress(id, n, sublabel?)     -> in-place update; stays persistent
 *   completeProgress(id, status='success'|'error')
 *                                        -> flips status; toast auto-dismisses
 *                                           after DEFAULT_TOAST_DURATION_MS
 *                                           (10 s); success toasts also reset
 *                                           progress to 100.
 *   removeProgress(id)                   -> immediate dismiss.
 */

'use client'

import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
} from 'react'

import {
  DEFAULT_TOAST_DURATION_MS,
  ToastProgress,
  useNotificationStore,
} from '@/stores/notificationStore'

export interface ProgressItem {
  id: string
  label: string
  sublabel?: string
  progress: number
  status: 'idle' | 'running' | 'success' | 'error'
  indeterminate?: boolean
  onCancel?: () => void
}

interface ProgressContextType {
  // Derived from the toast store: every toast with a `progress` payload.
  // Lets callers (and tests) introspect what's in flight without coupling
  // to the underlying notification store layout.
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
  const upsert = useNotificationStore((s) => s.upsertProgressToast)
  const remove = useNotificationStore((s) => s.removeToast)
  const toasts = useNotificationStore((s) => s.toasts)

  const progressItems = useMemo<ProgressItem[]>(
    () =>
      toasts
        .filter((t) => t.progress !== undefined)
        .map((t) => ({
          id: t.id,
          label: t.message,
          sublabel: t.progress!.sublabel,
          progress: t.progress!.progress,
          status: t.progress!.status,
          indeterminate: t.progress!.indeterminate,
          onCancel: t.progress!.onCancel,
        })),
    [toasts]
  )

  // Map of progress-id -> auto-dismiss timer handle. ProgressProvider is
  // the single owner of the progress-toast lifecycle — it arms the timer
  // when `completeProgress` flips status off 'running' and clears it on
  // restart or manual remove.
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(
    new Map()
  )
  const clearTimer = useCallback((id: string) => {
    const prev = timersRef.current.get(id)
    if (prev) {
      clearTimeout(prev)
      timersRef.current.delete(id)
    }
  }, [])

  useEffect(
    () => () => {
      timersRef.current.forEach((h) => clearTimeout(h))
      timersRef.current.clear()
    },
    []
  )

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
      // Restart of the same id: cancel any pending auto-dismiss from a
      // prior completion so the restarted progress doesn't vanish on us.
      clearTimer(id)
      const progress: ToastProgress = {
        progress: 0,
        status: 'running',
        sublabel: options?.sublabel,
        indeterminate: options?.indeterminate,
        onCancel: options?.onCancel,
      }
      upsert(id, label, progress)
    },
    [upsert, clearTimer]
  )

  const updateProgress = useCallback(
    (id: string, progress: number, sublabel?: string) => {
      const existing = useNotificationStore
        .getState()
        .toasts.find((t) => t.id === id)
      if (!existing) return
      const next: ToastProgress = {
        ...(existing.progress ?? { progress: 0, status: 'running' }),
        progress: Math.max(0, Math.min(100, progress)),
        sublabel:
          sublabel !== undefined ? sublabel : existing.progress?.sublabel,
      }
      upsert(id, existing.message, next)
    },
    [upsert]
  )

  const completeProgress = useCallback(
    (id: string, status: 'success' | 'error' = 'success') => {
      const existing = useNotificationStore
        .getState()
        .toasts.find((t) => t.id === id)
      if (!existing) return
      const next: ToastProgress = {
        ...(existing.progress ?? { progress: 100, status: 'running' }),
        progress: 100,
        status,
        // A finished operation is never indeterminate. Clear the flag so the
        // toast renders a filled bar with a percentage and a ✓/✗ icon — a
        // toast started with `indeterminate: true` would otherwise keep showing
        // the running shimmer (just recolored) and never look "done".
        indeterminate: false,
      }
      upsert(id, existing.message, next)
      // Arm the auto-dismiss. Honors the user-facing rule: progress toasts
      // stay until done, then behave like regular toasts (10 s default).
      // Applies to BOTH success AND error — error toasts used to be
      // sticky-forever in the old self-rolled overlay, but the unification
      // brings them under the standard toast lifecycle.
      clearTimer(id)
      const handle = setTimeout(() => {
        remove(id)
        timersRef.current.delete(id)
      }, DEFAULT_TOAST_DURATION_MS)
      timersRef.current.set(id, handle)
    },
    [upsert, remove, clearTimer]
  )

  const removeProgress = useCallback(
    (id: string) => {
      clearTimer(id)
      remove(id)
    },
    [remove, clearTimer]
  )

  const value = useMemo(
    () => ({
      progressItems,
      startProgress,
      updateProgress,
      completeProgress,
      removeProgress,
    }),
    [
      progressItems,
      startProgress,
      updateProgress,
      completeProgress,
      removeProgress,
    ]
  )

  return (
    <ProgressContext.Provider value={value}>
      {children}
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
