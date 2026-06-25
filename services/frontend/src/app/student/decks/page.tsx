'use client'

import { StudentSlotFallback } from '@/components/student/StudentSlotFallback'
import { useSlot } from '@/lib/extensions/slots'

export default function StudentDecksPage() {
  const StudentDecks = useSlot('StudentDecks')

  if (!StudentDecks) {
    return <StudentSlotFallback />
  }

  // eslint-disable-next-line react-hooks/static-components
  return <StudentDecks />
}
