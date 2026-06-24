'use client'

import { StudentSlotFallback } from '@/components/student/StudentSlotFallback'
import { useSlot } from '@/lib/extensions/slots'

export default function StudentLeaderboardPage() {
  const StudentLeaderboard = useSlot('StudentLeaderboard')

  if (!StudentLeaderboard) {
    return <StudentSlotFallback />
  }

  // eslint-disable-next-line react-hooks/static-components
  return <StudentLeaderboard />
}
