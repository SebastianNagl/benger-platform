/**
 * Session-expired redirect helper.
 *
 * Reuses the notificationStore's `flashRedirect` mechanism (URL-param encoded
 * toast that ToastProvider picks up on mount at the destination — see
 * Toast.tsx:157-181). Full-page navigation rather than client-side router
 * push, so auth state, WebSocket connections, and any other in-memory state
 * all reset cleanly.
 *
 * Use this when the server tells the client its session is no longer valid:
 *   - HTTP 401 from the API after refresh-token failure
 *   - WebSocket close codes 4401 (no/invalid token) or 4403 (no project access)
 *
 * The message is resolved via the non-React `translate()` helper so this
 * works from anywhere — components, Zustand stores, fetch wrappers, etc.
 * — without needing the I18nContext.
 */

import { translate } from '@/lib/utils/translate'
import { useNotificationStore } from '@/stores/notificationStore'

const DEFAULT_MESSAGE_KEY = 'toasts.auth.sessionExpired'

export function redirectToLoginAsExpired(messageKey: string = DEFAULT_MESSAGE_KEY): void {
  if (typeof window === 'undefined') {
    // SSR safety — no-op on the server. AuthContext's own initialization
    // flow handles auth state recovery on the next render.
    return
  }
  const message = translate(messageKey)
  const url = useNotificationStore
    .getState()
    .flashRedirect('/login', message, 'error')
  window.location.href = url
}
