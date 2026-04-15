/**
 * Session Validator Component
 *
 * Note: Session validation is now handled directly by AuthContext.
 * AuthContext manages SESSION_USER_KEY, user switching detection,
 * and cross-user contamination prevention automatically.
 *
 * This component is kept for backwards compatibility but does nothing.
 */

'use client'

export function SessionValidator() {
  // Session validation is now handled by AuthContext automatically
  // No additional validation needed here
  return null
}
