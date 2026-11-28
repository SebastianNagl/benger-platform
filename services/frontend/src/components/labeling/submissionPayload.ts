import type { AnnotationCreate, AnnotationResult } from '@/types/labelStudio'

/** The activity timing of one annotation session (useActivityTracker). */
export interface SubmissionTiming {
  activeMs: number
  focusedMs: number
  tabSwitches: number
}

/**
 * The body of a final annotation submission.
 *
 * Every submit path (the manual submit, the strict-timer auto-submit and the
 * annotation creator of the comparison modal) builds its body here, so each
 * stored annotation carries the same research fields: the lead time, the
 * activity timing and the instruction variant shown to the annotator. The
 * backend fills none of them itself.
 */
export function buildSubmissionPayload({
  result,
  leadTimeSeconds,
  timing,
  instructionVariant,
}: {
  result: AnnotationResult[]
  leadTimeSeconds: number
  timing: SubmissionTiming
  instructionVariant?: string | null
}): AnnotationCreate {
  return {
    result,
    was_cancelled: false,
    lead_time: leadTimeSeconds,
    active_duration_ms: timing.activeMs,
    focused_duration_ms: timing.focusedMs,
    tab_switches: timing.tabSwitches,
    instruction_variant: instructionVariant || undefined,
  }
}
