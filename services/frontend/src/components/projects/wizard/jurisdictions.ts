import { wizardJurisdictions, type Jurisdiction } from '@/lib/jurisdiction'

import type { WizardData } from './types'

/** The jurisdictions the wizard offers project types and templates for. */
export function wizardDataJurisdictions(
  organizations: Parameters<typeof wizardJurisdictions>[0],
  data: Pick<
    WizardData,
    'visibility' | 'organizationIds' | 'organizationGroupIds'
  >,
): Jurisdiction[] {
  return wizardJurisdictions(
    organizations,
    data.visibility === 'organization' ? data.organizationIds : null,
    data.organizationGroupIds,
  )
}
