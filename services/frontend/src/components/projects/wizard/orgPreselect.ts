import type { WizardData } from './types'

/**
 * Default a new project to the organization the user is working inside.
 *
 * Left private, a project cannot reach its organization's API keys: the
 * worker resolves keys per user, and an evaluation fails with "No API key
 * found" even though the organization has a key configured. That is what
 * made a configured organization key look missing on production.
 *
 * Only a fresh, untouched choice is changed. A visibility that is already
 * organization or public, or an organization list that is already filled
 * (by the user, a project-kind preset or an earlier call), is returned as
 * is, so a late-arriving organization context can never overwrite a
 * decision. Idempotent.
 */
export function preselectActiveOrganization(
  prev: WizardData,
  organization: { id: string } | null | undefined,
): WizardData {
  if (!organization) return prev
  if (prev.visibility !== 'private' || prev.organizationIds.length > 0) {
    return prev
  }
  return {
    ...prev,
    visibility: 'organization',
    organizationIds: [organization.id],
  }
}
