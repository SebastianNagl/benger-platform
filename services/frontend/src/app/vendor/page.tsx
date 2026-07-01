'use client'

import { StudentSlotFallback } from '@/components/student/StudentSlotFallback'
import { useSlot } from '@/lib/extensions/slots'

/**
 * Host route: /vendor. Mounts the extended VendorDashboard slot (Stripe Connect
 * onboarding, listing management, grants, human-grading queue). Renders the
 * generic slot fallback in the community edition where the slot is unregistered.
 */
export default function VendorPage() {
  const VendorDashboard = useSlot('VendorDashboard')

  if (!VendorDashboard) {
    return <StudentSlotFallback />
  }

  // eslint-disable-next-line react-hooks/static-components
  return <VendorDashboard />
}
