/**
 * Exam interface layout preference — the shared contract between the platform
 * (which stores the preference and owns the labeling render seam) and the
 * extended edition (which registers the modern layout renderer).
 *
 * A user picks in their profile how exam-shaped labeling interfaces render:
 *
 *   classic — today's stacked cards, each opening a full-screen modal.
 *   modern  — the Loesung editor is the always-open main sheet; the other
 *             fields dock as slide-in side panels (left/right/none).
 *
 * The platform never renders the modern layout itself: DynamicAnnotationInterface
 * delegates the fields region to the ModernExamLayout slot when (and only when)
 * the extended edition registered it, the user opted in, and the label config
 * is exam-shaped. Community edition: the slot never registers, every predicate
 * below stays false, rendering is byte-identical to today.
 */

import type { ComponentType, ReactNode } from 'react'

import type { ParsedComponent } from './parser'

export type ExamLayoutMode = 'classic' | 'modern'
export type ExamPanelSide = 'left' | 'right'
export type ExamPanelPosition = ExamPanelSide | 'none'

/**
 * Canonical layout preference object, exactly as stored in
 * users.exam_layout_prefs and validated by the API (ExamLayoutPrefs in
 * auth_schemas.py). The full object is always stored — including with
 * mode 'classic' — so a user's modern docking survives classic round-trips.
 * The case has no 'none': the exam text is mandatory.
 */
export interface ExamLayoutPrefs {
  mode: ExamLayoutMode
  case_position: ExamPanelSide
  notes_position: ExamPanelPosition
  outline_position: ExamPanelPosition
  /** Drag-resized overlay panel widths (px), per side; absent = default.
   *  Persisted so a width set in one exam applies to the next. */
  left_panel_width?: number
  right_panel_width?: number
}

/** Server-validated bounds for the drag-resizable panel widths (px). */
export const PANEL_WIDTH_MIN = 260
export const PANEL_WIDTH_MAX = 720
export const PANEL_WIDTH_DEFAULT = 384

/**
 * The resolved default: what every user gets until they configure the
 * preference (users.exam_layout_prefs = NULL), and the per-field fallback for
 * invalid stored values. Also the seed shown when the profile section first
 * switches to modern.
 */
export const CLASSIC_LAYOUT: ExamLayoutPrefs = Object.freeze({
  mode: 'classic',
  case_position: 'left',
  notes_position: 'right',
  outline_position: 'right',
})

/** Slot name the extended edition registers its modern layout renderer under. */
export const MODERN_EXAM_LAYOUT_SLOT = 'ModernExamLayout'

/**
 * Props contract of the ModernExamLayout slot component.
 *
 * The host (DynamicAnnotationInterface) keeps sole ownership of annotation
 * state, submit merging, autosave, and the action bar; the slot only arranges
 * WHERE each parsed node renders. It must render every field-producing node
 * exactly once via renderComponent — including fields the user placed 'none'
 * (those components stay mounted and render null, which keeps their drafts,
 * context registration, and heading sync alive).
 */
export interface ModernExamLayoutProps {
  /** Root of the parsed label_config (the <View> tree). */
  parsedConfig: ParsedComponent
  /**
   * The host's recursive renderer. Closes over the live componentValues and
   * the memoized change/annotation handlers, so calling it inside the slot is
   * exactly equivalent to the host's own classic call. Call it at most once
   * per node per render — Suspense keys derive from the key argument.
   */
  renderComponent: (config: ParsedComponent, key?: string) => ReactNode
  /** Resolved placements; mode is already verified to be 'modern'. */
  prefs: ExamLayoutPrefs
  readOnly?: boolean
  taskId?: string
}

export type ModernExamLayoutComponent = ComponentType<ModernExamLayoutProps>

const PANEL_SIDES: ReadonlySet<string> = new Set(['left', 'right'])
const PANEL_POSITIONS: ReadonlySet<string> = new Set(['left', 'right', 'none'])

/**
 * Total safe-parse of a stored preference value. The API validates every
 * write, so this is defense in depth against hand-edited rows and shape
 * evolution: any invalid or missing field falls back per-field to
 * CLASSIC_LAYOUT; a non-object (null, undefined, string, ...) resolves to
 * CLASSIC_LAYOUT wholesale. Never throws, never returns null.
 */
function resolvePanelWidth(raw: unknown): number | undefined {
  if (typeof raw !== 'number' || !Number.isFinite(raw)) return undefined
  return Math.min(PANEL_WIDTH_MAX, Math.max(PANEL_WIDTH_MIN, Math.round(raw)))
}

export function resolveExamLayoutPrefs(raw: unknown): ExamLayoutPrefs {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    return CLASSIC_LAYOUT
  }
  const value = raw as Record<string, unknown>
  const leftWidth = resolvePanelWidth(value.left_panel_width)
  const rightWidth = resolvePanelWidth(value.right_panel_width)
  return {
    mode: value.mode === 'modern' ? 'modern' : 'classic',
    case_position: PANEL_SIDES.has(value.case_position as string)
      ? (value.case_position as ExamPanelSide)
      : CLASSIC_LAYOUT.case_position,
    notes_position: PANEL_POSITIONS.has(value.notes_position as string)
      ? (value.notes_position as ExamPanelPosition)
      : CLASSIC_LAYOUT.notes_position,
    outline_position: PANEL_POSITIONS.has(value.outline_position as string)
      ? (value.outline_position as ExamPanelPosition)
      : CLASSIC_LAYOUT.outline_position,
    // Width keys appear only when valid — the canonical shape stays lean and
    // JSON.stringify drops nothing unexpected on the write path.
    ...(leftWidth !== undefined ? { left_panel_width: leftWidth } : {}),
    ...(rightWidth !== undefined ? { right_panel_width: rightWidth } : {}),
  }
}

/**
 * Whether a parsed label config is exam-shaped: it contains a Loesung output
 * field. The hardcoded tag name is an extension hook, not proprietary logic —
 * the same four tags are already listed in OUTPUT_COMPONENT_TYPES
 * (src/lib/labelConfig/fieldExtractor.ts); the component behind the tag lives
 * entirely in the extended edition.
 */
export function isExamShapedConfig(
  parsed: ParsedComponent | null | undefined
): boolean {
  if (!parsed) return false
  if (parsed.type === 'Loesung') return true
  return (parsed.children ?? []).some((child) => isExamShapedConfig(child))
}
