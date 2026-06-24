'use client'

import { StudentSlotFallback } from '@/components/student/StudentSlotFallback'
import { useSlot } from '@/lib/extensions/slots'

export default function StudentExamsListPage() {
  const StudentExamsList = useSlot('StudentExamsList')

  if (!StudentExamsList) {
    return <StudentSlotFallback />
  }

  // eslint-disable-next-line react-hooks/static-components
  return <StudentExamsList />
}
