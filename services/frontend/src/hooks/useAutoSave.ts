/**
 * useAutoSave Hook
 *
 * Provides automatic draft saving functionality for annotation interfaces.
 * Saves to localStorage only (local-only drafts for privacy).
 * Server saves only occur on final submission.
 *
 * Issue #1041: Auto-save for Gliederung/Loesung annotation fields
 * Issue #1110: Draft persistence on page refresh
 */

'use client'

import { AnnotationResult } from '@/types/labelStudio'
import { useCallback, useEffect, useRef, useState } from 'react'

// Constants
const LOCAL_STORAGE_KEY_PREFIX = 'benger_draft_'
const LOCAL_SAVE_DEBOUNCE_MS = 1000 // Save to localStorage after 1 second of inactivity

export interface DraftData {
  taskId: string
  annotations: AnnotationResult[]
  componentValues: Record<string, unknown>
  savedAt: number
  leadTime: number
}

export interface AutoSaveState {
  isSaving: boolean
  lastSaved: Date | null
  error: string | null
  hasDraft: boolean
  isImmediateSaving: boolean // True when user triggered immediate save (Ctrl+S)
}

export interface UseAutoSaveOptions {
  enabled?: boolean
  onError?: (error: Error) => void
  onSave?: () => void
}

/**
 * Get the localStorage key for a task's draft
 */
function getDraftKey(taskId: string): string {
  return `${LOCAL_STORAGE_KEY_PREFIX}${taskId}`
}

/**
 * Save draft to localStorage
 */
function saveDraftToLocal(data: DraftData): void {
  try {
    const key = getDraftKey(data.taskId)
    localStorage.setItem(key, JSON.stringify(data))
  } catch (error) {
    console.warn('Failed to save draft to localStorage:', error)
  }
}

/**
 * Load draft from localStorage
 */
function loadDraftFromLocal(taskId: string): DraftData | null {
  try {
    const key = getDraftKey(taskId)
    const stored = localStorage.getItem(key)
    if (stored) {
      return JSON.parse(stored)
    }
  } catch (error) {
    console.warn('Failed to load draft from localStorage:', error)
  }
  return null
}

/**
 * Clear draft from localStorage
 */
function clearDraftFromLocal(taskId: string): void {
  try {
    const key = getDraftKey(taskId)
    localStorage.removeItem(key)
  } catch (error) {
    console.warn('Failed to clear draft from localStorage:', error)
  }
}

/**
 * Hook for auto-saving annotation drafts
 */
export function useAutoSave(
  taskId: string | null,
  annotations: Map<string, AnnotationResult>,
  componentValues: Map<string, unknown>,
  startTime: number,
  options: UseAutoSaveOptions = {}
) {
  const { enabled = true } = options

  // Initialize state with draft check from localStorage
  const [state, setState] = useState<AutoSaveState>(() => {
    const draft = taskId ? loadDraftFromLocal(taskId) : null
    return {
      isSaving: false,
      lastSaved: draft ? new Date(draft.savedAt) : null,
      error: null,
      hasDraft: !!draft,
      isImmediateSaving: false,
    }
  })

  // Refs for debouncing
  const localSaveTimerRef = useRef<NodeJS.Timeout | null>(null)

  // Track if we have unsaved changes
  const hasChangesRef = useRef<boolean>(false)

  // Convert Maps to serializable format
  const serializeData = useCallback((): DraftData | null => {
    if (!taskId) return null

    const annotationsArray = Array.from(annotations.values())
    const valuesObject = Object.fromEntries(componentValues)
    const leadTime = Math.round((Date.now() - startTime) / 1000)

    return {
      taskId,
      annotations: annotationsArray,
      componentValues: valuesObject,
      savedAt: Date.now(),
      leadTime,
    }
  }, [taskId, annotations, componentValues, startTime])

  // Save to localStorage (debounced)
  const saveToLocal = useCallback(() => {
    const data = serializeData()
    if (data && data.annotations.length > 0) {
      saveDraftToLocal(data)
      setState((prev) => ({
        ...prev,
        lastSaved: new Date(),
        hasDraft: true,
      }))
      hasChangesRef.current = false
    }
  }, [serializeData])

  // Trigger local save with debounce
  const triggerSave = useCallback(() => {
    if (!enabled || !taskId) return

    hasChangesRef.current = true

    // Clear existing timer
    if (localSaveTimerRef.current) {
      clearTimeout(localSaveTimerRef.current)
    }

    // Debounce local save
    localSaveTimerRef.current = setTimeout(() => {
      saveToLocal()
    }, LOCAL_SAVE_DEBOUNCE_MS)
  }, [enabled, taskId, saveToLocal])

  // Trigger save when annotations or values change
  useEffect(() => {
    if (annotations.size > 0 || componentValues.size > 0) {
      triggerSave()
    }
  }, [annotations, componentValues, triggerSave])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (localSaveTimerRef.current) {
        clearTimeout(localSaveTimerRef.current)
      }
    }
  }, [])

  // Load draft data (from localStorage first, then server)
  const loadDraft = useCallback((): DraftData | null => {
    if (!taskId) return null
    return loadDraftFromLocal(taskId)
  }, [taskId])

  // Load draft from server - no longer used, drafts are local-only
  // Kept for API compatibility, always returns null
  const loadServerDraft = useCallback(async (): Promise<DraftData | null> => {
    return null
  }, [])

  // Clear draft (called after successful submission)
  // Drafts are local-only, so just clear from localStorage
  const clearDraft = useCallback(async () => {
    if (!taskId) return

    // Clear from localStorage
    clearDraftFromLocal(taskId)

    setState((prev) => ({
      ...prev,
      hasDraft: false,
      lastSaved: null,
    }))
    hasChangesRef.current = false
  }, [taskId])

  // Force save now (useful before navigation)
  // Drafts are local-only, so just saves to localStorage
  const forceSave = useCallback(async () => {
    saveToLocal()
  }, [saveToLocal])

  // Immediate save (for Ctrl+S) - saves to localStorage only
  // Accepts optional direct values to avoid race conditions with React state updates
  const saveNow = useCallback(async (
    directValues?: { fieldName: string; value: unknown }
  ): Promise<void> => {
    // If direct values provided, update componentValues immediately before saving
    // This avoids the race condition where React state hasn't propagated yet
    if (directValues) {
      componentValues.set(directValues.fieldName, directValues.value)
    }

    saveToLocal()
  }, [saveToLocal, componentValues])

  return {
    ...state,
    loadDraft,
    loadServerDraft,
    clearDraft,
    forceSave,
    saveNow,
    triggerSave,
  }
}

export default useAutoSave
