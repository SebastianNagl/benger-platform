/**
 * useServerDraftSync
 *
 * Periodic server-side draft sync for an annotation task: every 30s when the
 * result has changed, plus an immediate save when the tab is hidden. Upserts
 * into the ``task_drafts`` table via ``PUT /projects/{id}/tasks/{taskId}/draft``
 * for crash recovery and the strict-timer auto-submit fallback.
 *
 * A failed save is retried with backoff (5s, 10s, 20s, then the normal 30s) and
 * immediately when the browser reports it is back online. The hook returns the
 * sync status so the writing UI can warn when the server copy is stale
 * (``ServerDraftSyncWarning``); before, failures were swallowed silently and a
 * writer on a dead connection had no idea only their browser held the text.
 *
 * Extracted from LabelingInterface so the classic labeling page AND the student
 * exam attempt drive server drafts through one implementation (no duplicate
 * draft logic). The localStorage half of auto-save lives in ``useAutoSave``.
 *
 * NOTE: restorable draft *checkpoints* (the opt-in append-only snapshot history
 * used by exams) are NOT a community feature — that save/restore logic lives in
 * the extended ``DraftCheckpointPanel`` slot, mounted into LabelingInterface via
 * ``useSlot('DraftCheckpointPanel')``. This hook only owns the generic draft.
 */

'use client'

import { projectsAPI } from '@/lib/api/projects'
import { useEffect, useRef, useState } from 'react'

const SERVER_DRAFT_SYNC_MS = 30_000
const RETRY_BASE_MS = 5_000

export type ServerDraftSyncState = {
  /** 'idle' until the first save attempt, then the outcome of the latest one. */
  status: 'idle' | 'saved' | 'error'
  /** When the server last accepted a draft (null = not yet in this session). */
  lastSavedAt: Date | null
  /** Failed attempts since the last success (0 while healthy). */
  failures: number
}

const INITIAL_STATE: ServerDraftSyncState = {
  status: 'idle',
  lastSavedAt: null,
  failures: 0,
}

export function useServerDraftSync(
  projectId: string | undefined | null,
  taskId: string | undefined | null,
  annotations: any[],
  // `enabled: false` (read-only views: closed window, attempted tier) never
  // writes a draft: the server would 403 and there is nothing to recover.
  options: { enabled?: boolean } = {},
): ServerDraftSyncState {
  const enabled = options.enabled ?? true
  // Keep the latest annotations in a ref so the periodic timer below does NOT
  // list `annotations` in its effect deps: the parent's array reference can
  // churn many times per second, which would tear down and recreate the 30s
  // interval before it could ever fire (same failure + fix as TimerIntegration).
  const annotationsRef = useRef<any[]>(annotations)
  // Written from an effect rather than during render (react-hooks/refs):
  // identical net effect here, since the only reader is the 30s interval
  // below, which fires long after commit.
  useEffect(() => {
    annotationsRef.current = annotations
  })
  const lastSyncedRef = useRef<string>('[]')
  const [state, setState] = useState<ServerDraftSyncState>(INITIAL_STATE)

  // When the annotation set is cleared (most notably right after a submit
  // deletes the server draft), drop the de-dup baseline so re-entering even
  // identical content still re-persists on the next tick. Keyed on the
  // empty/non-empty boolean — NOT the churning array reference — so it never
  // tears down the interval below.
  const isEmpty = annotations.length === 0
  useEffect(() => {
    if (isEmpty) {
      lastSyncedRef.current = '[]'
      setState(INITIAL_STATE)
    }
  }, [isEmpty])

  // ── 30s live draft (task_drafts), + flush on tab-hide, + retry ───────────
  useEffect(() => {
    if (!enabled || !projectId || !taskId) return

    // Reset the de-dup baseline and status whenever the task changes.
    lastSyncedRef.current = '[]'
    setState(INITIAL_STATE)

    let cancelled = false
    let failures = 0
    let inFlight = false
    let retryTimer: ReturnType<typeof setTimeout> | null = null

    const syncDraft = async () => {
      if (inFlight) return
      const ann = annotationsRef.current ?? []
      const serialized = JSON.stringify(ann)
      if (serialized === lastSyncedRef.current) return
      if (ann.length === 0) return
      if (retryTimer) {
        clearTimeout(retryTimer)
        retryTimer = null
      }
      inFlight = true
      try {
        await projectsAPI.saveDraft(projectId, taskId, ann)
        lastSyncedRef.current = serialized
        failures = 0
        if (!cancelled) {
          setState({ status: 'saved', lastSavedAt: new Date(), failures: 0 })
        }
      } catch {
        // lastSyncedRef stays put, so the retry below re-sends this content
        // (or newer content, if the writer kept typing).
        failures += 1
        if (!cancelled) {
          setState((prev) => ({ ...prev, status: 'error', failures }))
          // Backoff 5s, 10s, 20s; after that the regular 30s tick takes over.
          const delay = RETRY_BASE_MS * 2 ** (failures - 1)
          if (delay < SERVER_DRAFT_SYNC_MS) {
            retryTimer = setTimeout(syncDraft, delay)
          }
        }
      } finally {
        inFlight = false
      }
    }

    const interval = setInterval(syncDraft, SERVER_DRAFT_SYNC_MS)

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') syncDraft()
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)
    window.addEventListener('online', syncDraft)

    return () => {
      cancelled = true
      clearInterval(interval)
      if (retryTimer) clearTimeout(retryTimer)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      window.removeEventListener('online', syncDraft)
    }
  }, [enabled, projectId, taskId])

  // A read-only view (or a just-submitted attempt) has nothing left to sync,
  // so it never reports a stale error from before it was disabled.
  return enabled ? state : INITIAL_STATE
}

export default useServerDraftSync
