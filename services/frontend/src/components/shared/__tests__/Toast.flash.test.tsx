/**
 * @jest-environment jsdom
 *
 * Behavior tests for ToastProvider's mount-time channels:
 *   1. Drains pendingFlashes from sessionStorage and dispatches them.
 *   2. Reads ?flash_msg/flash_type/flash_duration from window.location and
 *      strips them via history.replaceState.
 *   3. Rehydrates live toasts from sessionStorage with elapsed-time eviction
 *      and remaining-duration timer re-arming.
 *
 * These are the load-bearing edges of the post-redirect / F5-survival flow,
 * so they're worth exercising end-to-end (provider mount → toast renders).
 */

import { act, render, screen, waitFor } from '@testing-library/react'
import React from 'react'
import { ToastProvider } from '../Toast'
import {
  DEFAULT_TOAST_DURATION_MS,
  useNotificationStore,
} from '@/stores/notificationStore'

jest.unmock('@/components/shared/Toast')

jest.mock('framer-motion', () => ({
  motion: { div: ({ children, ...props }: any) => <div {...props}>{children}</div> },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (k: string) => k, locale: 'en' }),
}))

beforeEach(() => {
  jest.useFakeTimers({ now: 1_700_000_000_000 })
  useNotificationStore.setState({ toasts: [], pendingFlashes: [] })
  // Reset URL between tests.
  window.history.replaceState({}, '', '/')
})

afterEach(() => {
  jest.runOnlyPendingTimers()
  jest.useRealTimers()
})

describe('ToastProvider mount-time channels', () => {
  describe('pendingFlashes drain', () => {
    it('renders any pending flash as a toast on mount', () => {
      // Source page wrote a flash before redirecting; destination mounts now.
      useNotificationStore.getState().flash('welcome back', 'success', 8000)

      render(
        <ToastProvider>
          <div />
        </ToastProvider>
      )

      expect(screen.getByText('welcome back')).toBeInTheDocument()
      expect(screen.getByTestId('toast-item')).toHaveAttribute(
        'data-toast-type',
        'success'
      )
      // Flash was consumed — re-mounting shouldn't re-fire it.
      expect(useNotificationStore.getState().pendingFlashes).toHaveLength(0)
    })

    it('consumes each pending flash exactly once', () => {
      useNotificationStore.getState().flash('only-once', 'info')

      // First mount drains it.
      const { unmount } = render(
        <ToastProvider>
          <div />
        </ToastProvider>
      )
      expect(useNotificationStore.getState().pendingFlashes).toHaveLength(0)
      unmount()

      // Reset live toast list (but leave pendingFlashes intact, which is []).
      useNotificationStore.setState({ toasts: [] })

      // Second mount — no remaining flash to drain.
      render(
        <ToastProvider>
          <div />
        </ToastProvider>
      )
      expect(screen.queryAllByText('only-once')).toHaveLength(0)
    })
  })

  describe('URL flash query parameter', () => {
    it('reads ?flash_msg from URL, dispatches a toast, and strips the params', () => {
      window.history.replaceState(
        {},
        '',
        '/dashboard?flash_msg=hello&flash_type=success&keep=me'
      )

      render(
        <ToastProvider>
          <div />
        </ToastProvider>
      )

      expect(screen.getByText('hello')).toBeInTheDocument()
      expect(screen.getByTestId('toast-item')).toHaveAttribute(
        'data-toast-type',
        'success'
      )
      // flash_* params were stripped, unrelated params preserved.
      expect(window.location.search).toBe('?keep=me')
    })

    it('falls back to type "info" for an invalid flash_type', () => {
      window.history.replaceState(
        {},
        '',
        '/?flash_msg=msg&flash_type=bogus'
      )

      render(
        <ToastProvider>
          <div />
        </ToastProvider>
      )

      expect(screen.getByTestId('toast-item')).toHaveAttribute(
        'data-toast-type',
        'info'
      )
    })

    it('honors a custom flash_duration when present', () => {
      window.history.replaceState(
        {},
        '',
        '/?flash_msg=quick&flash_type=info&flash_duration=2000'
      )

      render(
        <ToastProvider>
          <div />
        </ToastProvider>
      )

      expect(screen.getByText('quick')).toBeInTheDocument()
      // Default would be 10s — verify the custom 2s timer fires before that.
      act(() => {
        jest.advanceTimersByTime(2000)
      })
      expect(screen.queryByText('quick')).not.toBeInTheDocument()
    })

    it('does nothing when the URL has no flash_msg parameter', () => {
      window.history.replaceState({}, '', '/dashboard?ref=email')

      render(
        <ToastProvider>
          <div />
        </ToastProvider>
      )

      expect(screen.queryByTestId('toast-item')).not.toBeInTheDocument()
      expect(window.location.search).toBe('?ref=email')
    })
  })

  describe('F5 rehydration of live toasts', () => {
    it('re-displays a partially-elapsed toast and re-arms the auto-dismiss timer', () => {
      // Simulate state as if a previous page-load fired a 10s toast 6s ago.
      const SIX_SECONDS_AGO = Date.now() - 6000
      useNotificationStore.setState({
        toasts: [
          {
            id: 'rehydrated',
            message: 'still showing',
            type: 'info',
            duration: DEFAULT_TOAST_DURATION_MS,
            createdAt: SIX_SECONDS_AGO,
          },
        ],
        pendingFlashes: [],
      })

      render(
        <ToastProvider>
          <div />
        </ToastProvider>
      )

      expect(screen.getByText('still showing')).toBeInTheDocument()

      // 3s later — still within the 10s window (4s remaining at mount).
      act(() => {
        jest.advanceTimersByTime(3000)
      })
      expect(screen.getByText('still showing')).toBeInTheDocument()

      // After the remaining 1s elapses, the re-armed timer fires.
      act(() => {
        jest.advanceTimersByTime(1500)
      })
      expect(screen.queryByText('still showing')).not.toBeInTheDocument()
    })

    it('evicts a toast whose duration has already elapsed at mount', () => {
      const ELEVEN_SECONDS_AGO = Date.now() - 11_000
      useNotificationStore.setState({
        toasts: [
          {
            id: 'expired',
            message: 'too late',
            type: 'info',
            duration: DEFAULT_TOAST_DURATION_MS,
            createdAt: ELEVEN_SECONDS_AGO,
          },
        ],
        pendingFlashes: [],
      })

      render(
        <ToastProvider>
          <div />
        </ToastProvider>
      )

      expect(screen.queryByText('too late')).not.toBeInTheDocument()
      expect(useNotificationStore.getState().toasts).toHaveLength(0)
    })

    it('keeps a persistent toast (duration === 0) across rehydrate forever', () => {
      useNotificationStore.setState({
        toasts: [
          {
            id: 'pinned',
            message: 'pinned error',
            type: 'error',
            duration: 0,
            createdAt: Date.now() - 60_000,
          },
        ],
        pendingFlashes: [],
      })

      render(
        <ToastProvider>
          <div />
        </ToastProvider>
      )

      expect(screen.getByText('pinned error')).toBeInTheDocument()

      act(() => {
        jest.advanceTimersByTime(DEFAULT_TOAST_DURATION_MS * 5)
      })
      // Still there — duration 0 means no auto-dismiss.
      expect(screen.getByText('pinned error')).toBeInTheDocument()
    })
  })
})
