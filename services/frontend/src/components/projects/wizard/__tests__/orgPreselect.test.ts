/**
 * A project created from inside an organization context must default to that
 * organization. Left private, the worker resolves API keys per user and every
 * AI feature fails with "No API key found", even when the organization has a
 * key configured.
 */
import { preselectActiveOrganization } from '../orgPreselect'
import { INITIAL_WIZARD_DATA } from '../types'

const LMU = { id: 'org-lmu' }

describe('preselectActiveOrganization', () => {
  it('preselects the active organization on a fresh wizard', () => {
    const next = preselectActiveOrganization(INITIAL_WIZARD_DATA, LMU)
    expect(next.visibility).toBe('organization')
    expect(next.organizationIds).toEqual(['org-lmu'])
  })

  it('changes nothing outside an organization context', () => {
    expect(preselectActiveOrganization(INITIAL_WIZARD_DATA, null)).toBe(
      INITIAL_WIZARD_DATA,
    )
    expect(preselectActiveOrganization(INITIAL_WIZARD_DATA, undefined)).toBe(
      INITIAL_WIZARD_DATA,
    )
  })

  it('never overrides a public choice', () => {
    const publicData = { ...INITIAL_WIZARD_DATA, visibility: 'public' as const }
    expect(preselectActiveOrganization(publicData, LMU)).toBe(publicData)
  })

  it('never overrides an organization list that is already filled', () => {
    const chosen = {
      ...INITIAL_WIZARD_DATA,
      visibility: 'organization' as const,
      organizationIds: ['org-other'],
    }
    expect(preselectActiveOrganization(chosen, LMU)).toBe(chosen)
  })

  it('is idempotent', () => {
    const once = preselectActiveOrganization(INITIAL_WIZARD_DATA, LMU)
    expect(preselectActiveOrganization(once, LMU)).toBe(once)
  })
})
