'use client'

import { ComplianceRouteShell } from '@/components/compliance/ComplianceSlot'
import { useParams } from 'next/navigation'

/**
 * Host route: /compliance/assessments/[assessmentId]. Mounts the compliance
 * overlay's `AssessmentDetail` slot with `{ assessmentId }` while the overlay
 * is active for the viewer, else a not-available notice.
 */
export default function ComplianceAssessmentPage() {
  const params = useParams<{ assessmentId: string }>()
  const assessmentId =
    typeof params?.assessmentId === 'string' ? params.assessmentId : ''
  return (
    <ComplianceRouteShell slot="AssessmentDetail" props={{ assessmentId }} />
  )
}
