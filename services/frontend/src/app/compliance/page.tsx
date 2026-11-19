'use client'

import { ComplianceRouteShell } from '@/components/compliance/ComplianceSlot'

/**
 * Host route: /compliance. Mounts the compliance overlay's
 * `ComplianceDashboard` slot while the overlay is active for the viewer,
 * else a not-available notice (community edition, flag off).
 */
export default function CompliancePage() {
  return <ComplianceRouteShell slot="ComplianceDashboard" />
}
