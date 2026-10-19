/**
 * Bridge from the API client to the feature flag store.
 *
 * When the server answers 404 with `detail.code === 'feature_disabled'`, a
 * feature (or a whole extension package, flag `extension.<id>`) was switched
 * off since this page loaded its flags. The API client reports every error
 * here; the flag store (./index.ts) installs the handler that refetches the
 * flags, so the UI hides what the server no longer serves.
 *
 * This module imports nothing, so lib/api/base.ts can use it without an
 * import cycle through the store (which itself calls the API client).
 */

export const FEATURE_DISABLED_CODE = 'feature_disabled'

let handler: (() => void) | null = null

/** Install (or clear) the reaction to a `feature_disabled` answer. */
export function setFeatureDisabledHandler(fn: (() => void) | null): void {
  handler = fn
}

/** Whether an error answer is a `feature_disabled` 404. */
export function isFeatureDisabledAnswer(
  status: number,
  errorData: unknown,
): boolean {
  if (status !== 404) return false
  const detail = (errorData as { detail?: unknown } | null)?.detail
  return (
    !!detail &&
    typeof detail === 'object' &&
    (detail as { code?: unknown }).code === FEATURE_DISABLED_CODE
  )
}

/** Called by the API client for every error answer; ignores everything else. */
export function reportFeatureDisabled(
  status: number,
  errorData: unknown,
): void {
  if (!isFeatureDisabledAnswer(status, errorData)) return
  try {
    handler?.()
  } catch {
    // A failing refetch must never change how the request itself fails.
  }
}
