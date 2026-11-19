'use client'

import { FeatureFlagGate } from '@/components/shared/FeatureFlagGate'
import { COMPLIANCE_RECORDS } from '@/lib/featureFlags/platformFlags'
import { ComplianceRouteShell } from '@/components/compliance/ComplianceSlot'
import { useParams } from 'next/navigation'

/**
 * Host route: /compliance/assessments/[assessmentId]. Mounts the compliance
 * overlay's `AssessmentDetail` slot with `{ assessmentId }` while the overlay
 * is active for the viewer, else a not-available notice.
 */
function ComplianceAssessmentPageContent() {
  const params = useParams<{ assessmentId: string }>()
  const assessmentId =
    typeof params?.assessmentId === 'string' ? params.assessmentId : ''
  return (
    <ComplianceRouteShell slot="AssessmentDetail" props={{ assessmentId }} />
  )
}

/** Behind the compliance_records flag: not found while it is off. */
export default function ComplianceAssessmentPage() {
  return (
    <FeatureFlagGate flag={COMPLIANCE_RECORDS}>
      <ComplianceAssessmentPageContent />
    </FeatureFlagGate>
  )
}
