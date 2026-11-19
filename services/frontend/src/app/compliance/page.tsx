'use client'

import { FeatureFlagGate } from '@/components/shared/FeatureFlagGate'
import { COMPLIANCE_RECORDS } from '@/lib/featureFlags/platformFlags'
import { ComplianceRouteShell } from '@/components/compliance/ComplianceSlot'

/**
 * Host route: /compliance. Mounts the compliance overlay's
 * `ComplianceDashboard` slot while the overlay is active for the viewer,
 * else a not-available notice (community edition, flag off).
 */
function CompliancePageContent() {
  return <ComplianceRouteShell slot="ComplianceDashboard" />
}

/** Behind the compliance_records flag: not found while it is off. */
export default function CompliancePage() {
  return (
    <FeatureFlagGate flag={COMPLIANCE_RECORDS}>
      <CompliancePageContent />
    </FeatureFlagGate>
  )
}
