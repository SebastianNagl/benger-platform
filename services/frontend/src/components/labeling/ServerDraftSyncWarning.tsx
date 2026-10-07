/**
 * ServerDraftSyncWarning
 *
 * Raises a persistent warning toast while ``useServerDraftSync`` cannot reach
 * the server, and replaces it with a short confirmation once a save goes
 * through again. The text is still kept in this browser (localStorage
 * auto-save) and the hook retries on its own, so the message reassures and
 * tells the writer not to close the tab rather than asking them to do
 * anything. Renders nothing itself.
 *
 * A toast rather than an inline banner because toasts sit above HeadlessUI
 * dialogs (z-60 vs. z-50): the answer editors open as fullscreen dialogs, and
 * a banner on the page behind them would be invisible exactly while the
 * writer is typing.
 *
 * One failed attempt is not enough to show it (a single dropped request on a
 * flaky network heals on the 5s retry); two in a row, or the browser reporting
 * offline, is.
 *
 * ``copy`` lets a host replace the title, body and recovery message, e.g. a
 * student surface that addresses writers informally; the last-saved line
 * stays shared.
 */

'use client'

import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import type { ServerDraftSyncState } from '@/hooks/useServerDraftSync'
import { useNotificationStore } from '@/stores/notificationStore'
import { useEffect, useRef } from 'react'

const MIN_FAILURES = 2

export function ServerDraftSyncWarning({
  sync,
  copy,
}: {
  sync: ServerDraftSyncState
  copy?: { title: string; body: string; restored?: string }
}) {
  const { t, locale } = useI18n()
  const { showToast, removeToast } = useToast()
  const toastIdRef = useRef<string | null>(null)

  const title: string = copy?.title ?? t('annotation.serverDraft.offlineTitle')
  const offline = typeof navigator !== 'undefined' && navigator.onLine === false
  const failing =
    sync.status === 'error' && (sync.failures >= MIN_FAILURES || offline)

  // Persistent toasts survive a reload (sessionStorage), but the hook that
  // would clear this one does not: drop a warning left over from before.
  useEffect(() => {
    const store = useNotificationStore.getState()
    for (const toast of store.toasts) {
      if (toast.type === 'warning' && toast.message.startsWith(`${title}.`)) {
        removeToast(toast.id)
      }
    }
    // Mount only: the title is stable for the life of the writing view.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (failing && toastIdRef.current === null) {
      const lastSaved = sync.lastSavedAt
        ? t('annotation.serverDraft.lastSaved', {
            time: sync.lastSavedAt.toLocaleTimeString(
              locale === 'en' ? 'en-GB' : 'de-DE',
              { hour: '2-digit', minute: '2-digit' },
            ),
          })
        : t('annotation.serverDraft.neverSaved')
      const body: string = copy?.body ?? t('annotation.serverDraft.offlineBody')
      toastIdRef.current = showToast(
        `${title}. ${body} ${lastSaved}`,
        'warning',
        0,
      )
    } else if (!failing && toastIdRef.current !== null) {
      removeToast(toastIdRef.current)
      toastIdRef.current = null
      if (sync.status === 'saved') {
        showToast(
          copy?.restored ?? t('annotation.serverDraft.restored'),
          'success',
        )
      }
    }
    // Only the failing edge matters; the message is fixed when it appears.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [failing])

  // Leaving the writing view (submit, navigation) clears the warning.
  useEffect(
    () => () => {
      if (toastIdRef.current !== null) removeToast(toastIdRef.current)
    },
    [removeToast],
  )

  return null
}

export default ServerDraftSyncWarning
