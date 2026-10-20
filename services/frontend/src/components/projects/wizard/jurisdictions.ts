import { wizardJurisdictions, type Jurisdiction } from '@/lib/jurisdiction'

import type { WizardData } from './types'

/** The jurisdictions the wizard offers project types and templates for. */
export function wizardDataJurisdictions(
  organizations: ReadonlyArray<{ id: string; jurisdiction?: unknown }>,
  data: Pick<WizardData, 'visibility' | 'organizationIds'>,
): Jurisdiction[] {
  return wizardJurisdictions(
    organizations,
    data.visibility === 'organization' ? data.organizationIds : null,
  )
}
