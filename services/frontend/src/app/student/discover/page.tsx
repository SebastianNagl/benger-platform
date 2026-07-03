'use client'

import { StudentSlotFallback } from '@/components/student/StudentSlotFallback'
import { useSlot } from '@/lib/extensions/slots'

export default function StudentDiscoverPage() {
  const StudentDiscover = useSlot('StudentDiscover')

  if (!StudentDiscover) {
    return <StudentSlotFallback />
  }

  // eslint-disable-next-line react-hooks/static-components
  return <StudentDiscover />
}
