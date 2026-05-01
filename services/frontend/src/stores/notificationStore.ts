/**
 * Notification (toast) store.
 *
 * Single source of truth for in-app toasts:
 *  - `toasts`: live, in-memory toast list rendered by `<ToastProvider>`.
 *  - `pendingFlashes`: explicit, persistent flash messages that survive
 *    a same-origin reload via the `persist` middleware (sessionStorage).
 *    `<ToastProvider>` drains them on mount.
 *
 * For cross-origin redirects (e.g. login -> org subdomain), sessionStorage
 * does not survive the host change. Use `flashRedirect(targetUrl, ...)` to
 * encode the flash as URL query parameters; `<ToastProvider>` reads them
 * on mount and strips them via `history.replaceState`.
 */

import { create } from 'zustand'
import {
  createJSONStorage,
  devtools,
  persist,
  subscribeWithSelector,
} from 'zustand/middleware'

export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface ToastItem {
  id: string
  type: ToastType
  message: string
  duration?: number // 0 = persistent (no auto-dismiss); undefined uses default
  // Wall-clock time the toast was created. Used by ToastProvider on rehydrate
  // to compute the remaining auto-dismiss window after a page reload.
  createdAt: number
}

interface NotificationState {
  toasts: ToastItem[]
  pendingFlashes: ToastItem[]
}

interface NotificationActions {
  addToast: (
    message: string,
    type?: ToastType,
    duration?: number
  ) => string
  removeToast: (id: string) => void
  clearToasts: () => void
  flash: (message: string, type?: ToastType, duration?: number) => void
  consumeFlashes: () => ToastItem[]
  flashRedirect: (
    targetUrl: string,
    message: string,
    type?: ToastType,
    duration?: number
  ) => string
}

export type NotificationStore = NotificationState & NotificationActions

export const DEFAULT_TOAST_DURATION_MS = 10_000
export const MAX_TOASTS = 5

const makeId = () => Math.random().toString(36).substring(2, 9)

export const useNotificationStore = create<NotificationStore>()(
  devtools(
    persist(
      subscribeWithSelector((set, get) => ({
        toasts: [],
        pendingFlashes: [],

        addToast: (
          message: string,
          type: ToastType = 'info',
          duration: number = DEFAULT_TOAST_DURATION_MS
        ) => {
          const id = makeId()
          const newToast: ToastItem = {
            id,
            type,
            message,
            duration,
            createdAt: Date.now(),
          }
          set(
            (state) => {
              // Dedup by message — reissuing the same string replaces the
              // old toast (e.g. progressively-updated loading messages).
              const filtered = state.toasts.filter(
                (t) => t.message !== message
              )
              return { toasts: [...filtered, newToast].slice(-MAX_TOASTS) }
            },
            false,
            'addToast'
          )
          return id
        },

        removeToast: (id: string) => {
          set(
            (state) => ({
              toasts: state.toasts.filter((t) => t.id !== id),
            }),
            false,
            'removeToast'
          )
        },

        clearToasts: () => {
          set({ toasts: [] }, false, 'clearToasts')
        },

        flash: (
          message: string,
          type: ToastType = 'info',
          duration: number = DEFAULT_TOAST_DURATION_MS
        ) => {
          const newFlash: ToastItem = {
            id: makeId(),
            type,
            message,
            duration,
            createdAt: Date.now(),
          }
          set(
            (state) => ({
              pendingFlashes: [...state.pendingFlashes, newFlash],
            }),
            false,
            'flash'
          )
        },

        consumeFlashes: () => {
          const { pendingFlashes } = get()
          if (pendingFlashes.length === 0) return []
          set({ pendingFlashes: [] }, false, 'consumeFlashes')
          return pendingFlashes
        },

        flashRedirect: (
          targetUrl: string,
          message: string,
          type: ToastType = 'info',
          duration: number = DEFAULT_TOAST_DURATION_MS
        ) => {
          // Cross-origin redirects can't read sessionStorage from the source
          // host — encode the flash as URL parameters instead.
          const base =
            typeof window !== 'undefined'
              ? window.location.href
              : 'http://localhost'
          const u = new URL(targetUrl, base)
          u.searchParams.set('flash_msg', message)
          u.searchParams.set('flash_type', type)
          if (duration !== DEFAULT_TOAST_DURATION_MS) {
            u.searchParams.set('flash_duration', String(duration))
          }
          return u.toString()
        },
      })),
      {
        name: 'benger-notifications',
        storage: createJSONStorage(() =>
          typeof window !== 'undefined' ? sessionStorage : (undefined as any)
        ),
        // Persist live toasts AND pending flashes. Each ToastItem carries a
        // createdAt timestamp; on rehydrate, ToastProvider computes the
        // remaining auto-dismiss window (duration - elapsed) and either
        // evicts the toast or re-arms a setTimeout for the remainder.
        // Persistent toasts (duration === 0) survive indefinitely.
        partialize: (state) => ({
          toasts: state.toasts,
          pendingFlashes: state.pendingFlashes,
        }),
      }
    )
  )
)
