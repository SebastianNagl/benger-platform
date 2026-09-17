/**
 * Error codes the LTI launch error page (/lti/error?code=...) explains.
 *
 * An LTI tool redirects the browser to that page when a launch from a
 * learning platform (Moodle, ILIAS) cannot complete. Pages that call the LTI
 * API forward a JSON error there too when its code is in this list. The list
 * mirrors the page codes of the tool's error registry (lti/errors.py in the
 * extension package), and a parity test there compares both lists. Add or
 * remove a code in both places.
 *
 * Each code names who can fix the problem, in the order the page lists them:
 * - reopen: start the activity again from the learning platform
 * - tryLater: a temporary server problem, try again in a few minutes
 * - teacher: the course teacher must act (for example link the activity)
 * - orgAdmin: the admin of the organization that runs the connection
 * - lmsAdmin: the admin of the learning platform (tool settings)
 * - support: the operator of this platform
 */

export const LTI_LAUNCH_ERROR_CODES = [
  'invalid_request',
  'registration_not_found',
  'registration_disabled',
  'org_inactive',
  'unknown_deployment',
  'deployment_disabled',
  'tool_not_configured',
  'state_unavailable',
  'invalid_state',
  'invalid_token',
  'nonce_mismatch',
  'nonce_reused',
  'unsupported_message',
  'not_linked',
  'exam_unavailable',
  'user_inactive',
  'membership_removed',
  'launch_expired',
  'launch_mismatch',
  'link_proof_failed',
  'account_not_linkable',
  'internal',
] as const

export type LtiLaunchErrorCode = (typeof LTI_LAUNCH_ERROR_CODES)[number]

export const LTI_ERROR_ACTION_CATEGORIES = [
  'reopen',
  'tryLater',
  'teacher',
  'orgAdmin',
  'lmsAdmin',
  'support',
] as const

export type LtiErrorAction = (typeof LTI_ERROR_ACTION_CATEGORIES)[number]

export const LTI_ERROR_ACTIONS: Readonly<
  Record<LtiLaunchErrorCode, readonly LtiErrorAction[]>
> = {
  invalid_request: ['reopen'],
  registration_not_found: ['lmsAdmin', 'orgAdmin'],
  registration_disabled: ['orgAdmin'],
  org_inactive: ['support'],
  unknown_deployment: ['lmsAdmin', 'orgAdmin'],
  deployment_disabled: ['orgAdmin'],
  tool_not_configured: ['support'],
  state_unavailable: ['tryLater'],
  invalid_state: ['reopen'],
  invalid_token: ['reopen', 'lmsAdmin'],
  nonce_mismatch: ['reopen'],
  nonce_reused: ['reopen'],
  unsupported_message: ['lmsAdmin'],
  not_linked: ['teacher'],
  exam_unavailable: ['teacher'],
  user_inactive: ['support'],
  membership_removed: ['orgAdmin'],
  launch_expired: ['reopen'],
  launch_mismatch: ['reopen'],
  link_proof_failed: ['reopen'],
  account_not_linkable: ['reopen', 'orgAdmin'],
  internal: ['tryLater'],
}

/** Actions for a code the page does not know. */
export const LTI_DEFAULT_ERROR_ACTIONS: readonly LtiErrorAction[] = ['reopen']

const CODE_SET: ReadonlySet<string> = new Set(LTI_LAUNCH_ERROR_CODES)

export function isLtiLaunchErrorCode(
  value: unknown,
): value is LtiLaunchErrorCode {
  return typeof value === 'string' && CODE_SET.has(value)
}

/** Who can fix the problem behind `code`, in display order. */
export function ltiErrorActions(
  code: string | null | undefined,
): readonly LtiErrorAction[] {
  return isLtiLaunchErrorCode(code)
    ? LTI_ERROR_ACTIONS[code]
    : LTI_DEFAULT_ERROR_ACTIONS
}

/**
 * Error page URL for a launch error code, or null when the code is not a
 * launch code (the calling page shows those errors itself).
 */
export function ltiLaunchErrorPath(
  code: string | null | undefined,
  ref?: string | null,
): string | null {
  if (!isLtiLaunchErrorCode(code)) return null
  const params = new URLSearchParams({ code })
  if (ref) params.set('ref', ref)
  return `/lti/error?${params.toString()}`
}
