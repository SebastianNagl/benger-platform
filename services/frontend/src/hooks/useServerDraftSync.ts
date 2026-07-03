/**
 * useServerDraftSync
 *
 * Periodic server-side draft sync for an annotation task: every 30s when the
 * result has changed, plus an immediate save when the tab is hidden. Upserts
 * into the ``task_drafts`` table via ``PUT /projects/{id}/tasks/{taskId}/draft``
 * for crash recovery and the strict-timer auto-submit fallback. Best-effort —
 * failures are swallowed.
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
import { useEffect, useRef } from 'react'

const SERVER_DRAFT_SYNC_MS = 30_000

export function useServerDraftSync(
  projectId: string | undefined | null,
  taskId: string | undefined | null,
  annotations: any[],
) {
  // Keep the latest annotations in a ref so the periodic timer below does NOT
  // list `annotations` in its effect deps: the parent's array reference can
  // churn many times per second, which would tear down and recreate the 30s
  // interval before it could ever fire (same failure + fix as TimerIntegration).
  const annotationsRef = useRef<any[]>(annotations)
  annotationsRef.current = annotations
  const lastSyncedRef = useRef<string>('[]')

  // When the annotation set is cleared (most notably right after a submit
  // deletes the server draft), drop the de-dup baseline so re-entering even
  // identical content still re-persists on the next tick. Keyed on the
  // empty/non-empty boolean — NOT the churning array reference — so it never
  // tears down the interval below.
  const isEmpty = annotations.length === 0
  useEffect(() => {
    if (isEmpty) {
      lastSyncedRef.current = '[]'
    }
  }, [isEmpty])

  // ── 30s live draft (task_drafts), + flush on tab-hide ──────────────────────
  useEffect(() => {
    if (!projectId || !taskId) return

    // Reset the de-dup baseline whenever the task changes.
    lastSyncedRef.current = '[]'

    const syncDraft = async () => {
      const ann = annotationsRef.current ?? []
      const serialized = JSON.stringify(ann)
      if (serialized === lastSyncedRef.current) return
      if (ann.length === 0) return
      try {
        await projectsAPI.saveDraft(projectId, taskId, ann)
        lastSyncedRef.current = serialized
      } catch {
        // Silent failure — draft sync is best-effort.
      }
    }

    const interval = setInterval(syncDraft, SERVER_DRAFT_SYNC_MS)

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') syncDraft()
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      clearInterval(interval)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [projectId, taskId])
}

export default useServerDraftSync
