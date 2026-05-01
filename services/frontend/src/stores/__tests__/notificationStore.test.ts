/**
 * @jest-environment jsdom
 */

import {
  DEFAULT_TOAST_DURATION_MS,
  MAX_TOASTS,
  useNotificationStore,
} from '../notificationStore'

describe('NotificationStore', () => {
  beforeEach(() => {
    useNotificationStore.setState({
      toasts: [],
      pendingFlashes: [],
    })
    sessionStorage.clear()
  })

  describe('addToast', () => {
    it('adds a toast with a generated id and the default duration', () => {
      const id = useNotificationStore.getState().addToast('hello', 'success')

      const state = useNotificationStore.getState()
      expect(id).toBeTruthy()
      expect(state.toasts).toHaveLength(1)
      expect(state.toasts[0]).toMatchObject({
        id,
        type: 'success',
        message: 'hello',
        duration: DEFAULT_TOAST_DURATION_MS,
      })
    })

    it('defaults to type "info" when type is omitted', () => {
      useNotificationStore.getState().addToast('hello')
      expect(useNotificationStore.getState().toasts[0].type).toBe('info')
    })

    it('respects a custom duration', () => {
      useNotificationStore.getState().addToast('hello', 'info', 3000)
      expect(useNotificationStore.getState().toasts[0].duration).toBe(3000)
    })

    it('caps the toast list at MAX_TOASTS, evicting oldest first', () => {
      const { addToast } = useNotificationStore.getState()
      for (let i = 0; i < MAX_TOASTS + 2; i++) {
        addToast(`toast-${i}`, 'info')
      }
      const state = useNotificationStore.getState()
      expect(state.toasts).toHaveLength(MAX_TOASTS)
      expect(state.toasts[0].message).toBe(`toast-2`)
      expect(state.toasts[MAX_TOASTS - 1].message).toBe(
        `toast-${MAX_TOASTS + 1}`
      )
    })

    it('dedups by message — re-adding the same message replaces the old toast', () => {
      const { addToast } = useNotificationStore.getState()
      addToast('loading', 'info')
      const id2 = addToast('loading', 'info')

      const state = useNotificationStore.getState()
      expect(state.toasts).toHaveLength(1)
      expect(state.toasts[0].id).toBe(id2)
    })

    it('generates unique ids', () => {
      const { addToast } = useNotificationStore.getState()
      const ids = new Set<string>()
      for (let i = 0; i < 50; i++) ids.add(addToast(`msg-${i}`))
      expect(ids.size).toBe(50)
    })
  })

  describe('removeToast / clearToasts', () => {
    it('removes a toast by id', () => {
      const { addToast, removeToast } = useNotificationStore.getState()
      const id1 = addToast('a', 'info')
      const id2 = addToast('b', 'info')

      removeToast(id1)

      const state = useNotificationStore.getState()
      expect(state.toasts).toHaveLength(1)
      expect(state.toasts[0].id).toBe(id2)
    })

    it('is a no-op for an unknown id', () => {
      const { addToast, removeToast } = useNotificationStore.getState()
      addToast('a', 'info')
      removeToast('missing')
      expect(useNotificationStore.getState().toasts).toHaveLength(1)
    })

    it('clearToasts removes everything', () => {
      const { addToast, clearToasts } = useNotificationStore.getState()
      addToast('a', 'info')
      addToast('b', 'info')
      clearToasts()
      expect(useNotificationStore.getState().toasts).toHaveLength(0)
    })
  })

  describe('flash / consumeFlashes', () => {
    it('flash() pushes onto pendingFlashes without touching toasts', () => {
      const { flash } = useNotificationStore.getState()
      flash('welcome back', 'success')

      const state = useNotificationStore.getState()
      expect(state.toasts).toHaveLength(0)
      expect(state.pendingFlashes).toHaveLength(1)
      expect(state.pendingFlashes[0]).toMatchObject({
        type: 'success',
        message: 'welcome back',
        duration: DEFAULT_TOAST_DURATION_MS,
      })
    })

    it('consumeFlashes() returns and clears pendingFlashes', () => {
      const { flash, consumeFlashes } = useNotificationStore.getState()
      flash('a', 'success')
      flash('b', 'error')

      const drained = consumeFlashes()
      expect(drained).toHaveLength(2)
      expect(drained.map((f) => f.message)).toEqual(['a', 'b'])
      expect(useNotificationStore.getState().pendingFlashes).toHaveLength(0)
    })

    it('consumeFlashes() returns [] when there are no pending flashes', () => {
      expect(useNotificationStore.getState().consumeFlashes()).toEqual([])
    })
  })

  describe('flashRedirect', () => {
    it('encodes message and type as URL parameters', () => {
      const url = useNotificationStore
        .getState()
        .flashRedirect('https://app.example.com/dashboard', 'welcome', 'success')

      const u = new URL(url)
      expect(u.origin + u.pathname).toBe('https://app.example.com/dashboard')
      expect(u.searchParams.get('flash_msg')).toBe('welcome')
      expect(u.searchParams.get('flash_type')).toBe('success')
      // Default duration is implicit — no query param needed.
      expect(u.searchParams.get('flash_duration')).toBeNull()
    })

    it('encodes a non-default duration explicitly', () => {
      const url = useNotificationStore
        .getState()
        .flashRedirect(
          'https://app.example.com/x',
          'pinned',
          'warning',
          0
        )
      expect(new URL(url).searchParams.get('flash_duration')).toBe('0')
    })

    it('preserves existing query parameters on the target URL', () => {
      const url = useNotificationStore
        .getState()
        .flashRedirect(
          'https://app.example.com/x?ref=email',
          'hi',
          'info'
        )
      const u = new URL(url)
      expect(u.searchParams.get('ref')).toBe('email')
      expect(u.searchParams.get('flash_msg')).toBe('hi')
    })
  })

  describe('persistence', () => {
    it('persists pendingFlashes to sessionStorage but not live toasts', async () => {
      const { addToast, flash } = useNotificationStore.getState()
      addToast('live-toast', 'info')
      flash('persistent-flash', 'success')

      // The persist middleware writes synchronously after mutations on
      // jsdom/sessionStorage, but commits happen on next microtask — give
      // it a tick before reading the storage payload.
      await Promise.resolve()

      const raw = sessionStorage.getItem('benger-notifications')
      expect(raw).toBeTruthy()
      const persisted = JSON.parse(raw as string)
      expect(persisted.state.pendingFlashes).toHaveLength(1)
      expect(persisted.state.pendingFlashes[0].message).toBe(
        'persistent-flash'
      )
      // Live toasts ARE persisted (with createdAt) so F5 keeps them on
      // screen for the remainder of their duration. ToastProvider re-arms
      // the auto-dismiss timer based on `duration - (now - createdAt)`.
      expect(persisted.state.toasts).toHaveLength(1)
      expect(persisted.state.toasts[0].message).toBe('live-toast')
      expect(typeof persisted.state.toasts[0].createdAt).toBe('number')
    })
  })
})
