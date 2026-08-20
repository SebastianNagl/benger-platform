'use client'

import { StudentSlotFallback } from '@/components/student/StudentSlotFallback'
import { useSlot } from '@/lib/extensions/slots'

export default function StudentBuilderPage() {
  const StudentBuilder = useSlot('StudentBuilder')

  if (!StudentBuilder) {
    return <StudentSlotFallback />
  }

  // eslint-disable-next-line react-hooks/static-components
  return <StudentBuilder />
}
