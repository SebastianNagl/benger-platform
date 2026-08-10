'use client'

/**
 * useModernExamLayout — the single predicate for whether the modern exam
 * layout renders, and the handle to the slot component that renders it.
 *
 * Layering (mirrors useResolvedUiMode's two-layer guard):
 *   1. Community edition → inactive (the modern renderer is extended-only).
 *   2. ModernExamLayout slot not registered (extended bundle absent or still
 *      loading) → inactive. useSlot subscribes to registrations, so a late
 *      loadExtended() flips the result without a reload.
 *   3. User preference (users.exam_layout_prefs via the auth user object,
 *      safe-parsed) must be mode 'modern'.
 *   4. The label config must be exam-shaped (contains a Loesung field) —
 *      the preference only applies to exams, never to generic annotation
 *      projects.
 *
 * Hosts additionally opt in per mount point (allowModernLayout on
 * DynamicAnnotationInterface), which keeps read-only review surfaces classic.
 */

import { useMemo } from 'react'

import { useOptionalAuth } from '@/contexts/AuthContext'
import { isExtendedEdition } from '@/hooks/useResolvedUiMode'
import {
  isExamShapedConfig,
  MODERN_EXAM_LAYOUT_SLOT,
  resolveExamLayoutPrefs,
  type ExamLayoutPrefs,
  type ModernExamLayoutComponent,
} from '@/lib/labelConfig/examLayout'
import { parseLabelConfig } from '@/lib/labelConfig/parser'
import { useSlot } from '@/lib/extensions/slots'

export interface ModernExamLayoutState {
  /** True iff every layer above resolves to the modern layout. */
  active: boolean
  /** Resolved preference (total — falls back to classic defaults). */
  prefs: ExamLayoutPrefs
  /** The registered slot component; null while unregistered. */
  Layout: ModernExamLayoutComponent | null
}

export function useModernExamLayout(
  labelConfig: string | null | undefined
): ModernExamLayoutState {
  const Layout = useSlot(
    MODERN_EXAM_LAYOUT_SLOT
  ) as ModernExamLayoutComponent | null
  // Optional: DynamicAnnotationInterface must stay mountable without an
  // AuthProvider (isolated tests, review surfaces). No auth -> classic.
  const user = useOptionalAuth()?.user

  const prefs = useMemo(
    () => resolveExamLayoutPrefs(user?.exam_layout_prefs),
    [user?.exam_layout_prefs]
  )

  const examShaped = useMemo(() => {
    if (!labelConfig) return false
    const parsed = parseLabelConfig(labelConfig)
    if ('message' in parsed) return false
    return isExamShapedConfig(parsed)
  }, [labelConfig])

  const active =
    isExtendedEdition() && !!Layout && prefs.mode === 'modern' && examShaped

  return { active, prefs, Layout }
}
