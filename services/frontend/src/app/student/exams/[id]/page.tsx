'use client'

import { StudentSlotFallback } from '@/components/student/StudentSlotFallback'
import { useSlot } from '@/lib/extensions/slots'
import { useParams } from 'next/navigation'

export default function StudentExamDetailPage() {
  const params = useParams<{ id: string }>()
  const examId = params!.id
  const StudentExamDetail = useSlot('StudentExamDetail')

  if (!StudentExamDetail) {
    return <StudentSlotFallback />
  }

  // eslint-disable-next-line react-hooks/static-components
  return <StudentExamDetail examId={examId} />
}
