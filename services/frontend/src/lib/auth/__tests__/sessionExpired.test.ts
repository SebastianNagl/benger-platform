/**
 * @jest-environment jsdom
 */
import { useNotificationStore } from '@/stores/notificationStore'

// Mock the notificationStore so we can assert what `flashRedirect` was
// called with without actually firing a navigation. JSDOM makes
// `window.location.href` non-configurable, so stubbing the redirect
// directly is the cleanest route.
const mockFlashRedirect = jest.fn(
  (target: string, msg: string) =>
    `${target}?flash_msg=${encodeURIComponent(msg)}&flash_type=error`
)

jest.mock('@/stores/notificationStore', () => ({
  useNotificationStore: {
    getState: () => ({
      flashRedirect: mockFlashRedirect,
    }),
  },
}))

// Import AFTER the mock is set up.
import { redirectToLoginAsExpired } from '../sessionExpired'

describe('redirectToLoginAsExpired', () => {
  beforeEach(() => {
    mockFlashRedirect.mockClear()
  })

  it('calls flashRedirect with /login, the default translated message, and error type', () => {
    // Swallow the JSDOM "not implemented: navigation" warning the
    // assignment triggers when window.location.href is set. The helper's
    // actual navigation is exercised at runtime; the unit test just
    // confirms it dispatched the flashRedirect call with the right args.
    const originalError = console.error
    console.error = jest.fn()

    try {
      redirectToLoginAsExpired()
    } catch {
      // Some JSDOM versions throw on assignment to location.href.
      // The flashRedirect call has already happened by then.
    }

    expect(mockFlashRedirect).toHaveBeenCalledTimes(1)
    const [target, message, type] = mockFlashRedirect.mock.calls[0]
    expect(target).toBe('/login')
    expect(typeof message).toBe('string')
    expect(message.length).toBeGreaterThan(0)
    expect(type).toBe('error')

    console.error = originalError
  })

  it('accepts a custom message key', () => {
    const originalError = console.error
    console.error = jest.fn()

    try {
      redirectToLoginAsExpired('errors.annotation.user.sessionExpired')
    } catch {
      // see above
    }

    expect(mockFlashRedirect).toHaveBeenCalledTimes(1)
    const [, message] = mockFlashRedirect.mock.calls[0]
    expect(typeof message).toBe('string')
    expect(message.length).toBeGreaterThan(0)

    console.error = originalError
  })
})
