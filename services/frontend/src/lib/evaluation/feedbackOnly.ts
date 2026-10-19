/**
 * Score-less judge results (core 2.41): an overlay judge that writes
 * feedback instead of a score stores `value: null` with
 * `details.feedback_only: true` and `passed: true` ("the feedback exists").
 * Views must not render that `passed` as a pass/fail verdict.
 */
export function isFeedbackOnlyResult(
  metrics: Record<string, unknown> | null | undefined,
): boolean {
  if (!metrics || typeof metrics !== 'object') return false
  return Object.values(metrics).some((blob) => {
    if (!blob || typeof blob !== 'object') return false
    const details = (blob as { details?: unknown }).details
    return (
      !!details &&
      typeof details === 'object' &&
      (details as { feedback_only?: unknown }).feedback_only === true
    )
  })
}
