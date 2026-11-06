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
 *   state   - a state-specific interface imitating that Bundesland's e-exam
 *             software (state_code). The same slot renders it; it also takes
 *             over the host's chrome (timer, leave, submit) via `chrome`.
 *
 * The platform never renders the modern layout itself: DynamicAnnotationInterface
 * delegates the fields region to the ModernExamLayout slot when (and only when)
 * the extended edition registered it, the user opted in, and the label config
 * is exam-shaped. Community edition: the slot never registers, every predicate
 * below stays false, rendering is byte-identical to today.
 */

import type { ComponentType, ReactNode } from 'react'

import {
  isBundeslandCode,
  type BundeslandCode,
} from '@/lib/profile/bundeslaender'

import type { ParsedComponent } from './parser'

export type ExamLayoutMode = 'classic' | 'modern' | 'state'
export type ExamSheetAlign = 'left' | 'center' | 'right' | 'justify'
export type ExamStateTheme = 'standard' | 'contrast'

/** Display-only settings of a state-specific interface. `align` is how the
 *  whole sheet is shown (the stored Lösung stays plain markdown); `hide_time`
 *  hides the remaining-time readout while the timer keeps running; `theme`
 *  is the interface's colour scheme; `spellcheck` toggles the browser's
 *  spell checking in the writing sheet. */
export interface ExamStateUiPrefs {
  align?: ExamSheetAlign
  hide_time?: boolean
  theme?: ExamStateTheme
  spellcheck?: boolean
}
export type ExamPanelSide = 'left' | 'right'
export type ExamPanelPosition = ExamPanelSide | 'none'

/** Where an exam tool (calculator, law texts, ...) sits in the modern
 *  layout: a bookmark on a side rail, a floating in-page window, or hidden. */
export type ExamToolZone = 'left' | 'right' | 'float' | 'hidden'

/** A tool's placement, keyed by tool id in `tool_placements`. `order` sorts
 *  tools within a rail. `width` is the rail panel width (px); `x`, `y`, `w`,
 *  `h` the floating window box in percent of the viewport. */
export interface ExamToolPlacement {
  zone: ExamToolZone
  order?: number
  width?: number
  x?: number
  y?: number
  w?: number
  h?: number
}

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
  /** Mode 'state': which state's exam software the interface imitates. Kept
   *  across mode switches so switching back restores it. */
  state_code?: BundeslandCode
  state_ui?: ExamStateUiPrefs
  /** Mode 'modern': where each exam tool sits, by tool id. Tools without an
   *  entry use the interface's defaults. */
  tool_placements?: Record<string, ExamToolPlacement>
}

/** Server-validated bounds for the drag-resizable panel widths (px). */
export const PANEL_WIDTH_MIN = 260
export const PANEL_WIDTH_MAX = 720
export const PANEL_WIDTH_DEFAULT = 384

/** Server-validated bounds of `tool_placements` (ExamToolPlacement in
 *  auth_schemas.py). */
export const TOOL_ID_PATTERN = /^[a-z_]{1,40}$/
export const TOOL_PLACEMENTS_MAX = 20
export const TOOL_ORDER_MAX = 50
/** Smallest floating window, percent of the viewport per axis. */
export const TOOL_FLOAT_MIN = 10

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
  /** Resolved placements; mode is already verified to be 'modern' or 'state'. */
  prefs: ExamLayoutPrefs
  readOnly?: boolean
  taskId?: string
  /** Mode 'state': host chrome the state interface renders itself. Mode
   *  'modern' (core 2.50): only `renderTools`, rendered inside the layout. */
  chrome?: ExamChrome
}

/**
 * Host chrome handed to the layout slot in mode 'state', whose interface
 * replaces the host's own header (timer, back button) and action bar. The
 * host keeps owning the behaviour: renderTimer renders the host's timer
 * (same session, same expiry handling incl. strict auto-submit), onSubmit is
 * the host's own submit path.
 */
/** Visual variants of the exam tools (ExamChrome.renderTools). */
export type ExamToolsVariant = 'default' | 'state' | 'modern'

export interface ExamChrome {
  /** Renders the host's timer in the given visual variant; null when the
   *  attempt has no time limit. */
  renderTimer?: (variant: 'default' | 'state') => ReactNode
  /** Leave the attempt without submitting (draft is kept). */
  onLeave?: () => void
  /** Title of the exam or project, for interfaces that show it. */
  title?: string
  /** Extra host controls (e.g. restorable checkpoints) to place in the bar. */
  extra?: ReactNode
  /** Renders the project's exam tools (calculator, law texts, ...; the
   *  ExamToolDock slot) in the given visual variant. A state interface places
   *  the 'state' variant in its own chrome and the modern layout the
   *  'modern' variant inside its own layout context (core 2.50); the classic
   *  render shows the 'default' variant. Undefined when the host offers no
   *  tools. */
  renderTools?: (variant: ExamToolsVariant) => ReactNode
  /** Supplied by DynamicAnnotationInterface: its merged submit. */
  onSubmit?: () => void
  canSubmit?: boolean
  requireConfirmBeforeSubmit?: boolean
}

/** What a host passes to DynamicAnnotationInterface (examChrome prop). */
export type HostExamChrome = Pick<
  ExamChrome,
  'renderTimer' | 'onLeave' | 'extra' | 'title' | 'renderTools'
>

export type ModernExamLayoutComponent = ComponentType<ModernExamLayoutProps>

const PANEL_SIDES: ReadonlySet<string> = new Set(['left', 'right'])
const PANEL_POSITIONS: ReadonlySet<string> = new Set(['left', 'right', 'none'])
const SHEET_ALIGNS: ReadonlySet<string> = new Set([
  'left',
  'center',
  'right',
  'justify',
])
const STATE_THEMES: ReadonlySet<string> = new Set(['standard', 'contrast'])

function resolveStateUi(raw: unknown): ExamStateUiPrefs | undefined {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    return undefined
  }
  const value = raw as Record<string, unknown>
  const out: ExamStateUiPrefs = {}
  if (SHEET_ALIGNS.has(value.align as string)) {
    out.align = value.align as ExamSheetAlign
  }
  if (typeof value.hide_time === 'boolean') out.hide_time = value.hide_time
  if (STATE_THEMES.has(value.theme as string)) {
    out.theme = value.theme as ExamStateTheme
  }
  if (typeof value.spellcheck === 'boolean') out.spellcheck = value.spellcheck
  return Object.keys(out).length > 0 ? out : undefined
}

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

const TOOL_ZONES: ReadonlySet<string> = new Set([
  'left',
  'right',
  'float',
  'hidden',
])

function finiteNumber(raw: unknown): number | undefined {
  return typeof raw === 'number' && Number.isFinite(raw) ? raw : undefined
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

/** Safe-parse of `tool_placements`: invalid entries are dropped, numbers are
 *  clamped to the server bounds, a floating box always fits the viewport. */
export function resolveToolPlacements(
  raw: unknown,
): Record<string, ExamToolPlacement> | undefined {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    return undefined
  }
  const out: Record<string, ExamToolPlacement> = {}
  for (const [id, entry] of Object.entries(raw as Record<string, unknown>)) {
    if (Object.keys(out).length >= TOOL_PLACEMENTS_MAX) break
    if (!TOOL_ID_PATTERN.test(id)) continue
    if (typeof entry !== 'object' || entry === null) continue
    const value = entry as Record<string, unknown>
    if (!TOOL_ZONES.has(value.zone as string)) continue
    const placement: ExamToolPlacement = { zone: value.zone as ExamToolZone }
    const order = finiteNumber(value.order)
    if (order !== undefined) {
      placement.order = clamp(Math.round(order), 0, TOOL_ORDER_MAX)
    }
    const width = resolvePanelWidth(value.width)
    if (width !== undefined) placement.width = width
    const w = finiteNumber(value.w)
    const h = finiteNumber(value.h)
    if (w !== undefined) placement.w = clamp(w, TOOL_FLOAT_MIN, 100)
    if (h !== undefined) placement.h = clamp(h, TOOL_FLOAT_MIN, 100)
    const x = finiteNumber(value.x)
    const y = finiteNumber(value.y)
    if (x !== undefined) placement.x = clamp(x, 0, 100 - (placement.w ?? 0))
    if (y !== undefined) placement.y = clamp(y, 0, 100 - (placement.h ?? 0))
    out[id] = placement
  }
  return Object.keys(out).length > 0 ? out : undefined
}

export function resolveExamLayoutPrefs(raw: unknown): ExamLayoutPrefs {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    return CLASSIC_LAYOUT
  }
  const value = raw as Record<string, unknown>
  const leftWidth = resolvePanelWidth(value.left_panel_width)
  const rightWidth = resolvePanelWidth(value.right_panel_width)
  const stateCode = isBundeslandCode(value.state_code)
    ? value.state_code
    : undefined
  const stateUi = resolveStateUi(value.state_ui)
  const toolPlacements = resolveToolPlacements(value.tool_placements)
  // 'state' without a valid state_code has nothing to render -> classic.
  const mode: ExamLayoutMode =
    value.mode === 'modern'
      ? 'modern'
      : value.mode === 'state' && stateCode
        ? 'state'
        : 'classic'
  return {
    mode,
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
    ...(stateCode ? { state_code: stateCode } : {}),
    ...(stateUi ? { state_ui: stateUi } : {}),
    ...(toolPlacements ? { tool_placements: toolPlacements } : {}),
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
  parsed: ParsedComponent | null | undefined,
): boolean {
  if (!parsed) return false
  if (parsed.type === 'Loesung') return true
  return (parsed.children ?? []).some((child) => isExamShapedConfig(child))
}
