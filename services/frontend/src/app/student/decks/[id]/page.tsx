'use client'

import { StudentSlotFallback } from '@/components/student/StudentSlotFallback'
import { useSlot } from '@/lib/extensions/slots'
import { useParams } from 'next/navigation'

export default function StudentDeckDetailPage() {
  const params = useParams<{ id: string }>()
  const deckId = params!.id
  const StudentDeckDetail = useSlot('StudentDeckDetail')

  if (!StudentDeckDetail) {
    return <StudentSlotFallback />
  }

  // eslint-disable-next-line react-hooks/static-components
  return <StudentDeckDetail deckId={deckId} />
}
