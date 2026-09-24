/**
 * Labeling page - Label Studio aligned annotation interface
 *
 * This page provides the single-task annotation interface with keyboard shortcuts
 */

'use client'

import { ProtectedRoute } from '@/components/auth/ProtectedRoute'
import { LabelingInterface } from '@/components/labeling/LabelingInterface'
import { useSlot } from '@/lib/extensions/slots'
import { use } from 'react'

interface LabelingPageProps {
  params: Promise<{
    id: string
  }>
}

export default function LabelingPage({ params }: LabelingPageProps) {
  const resolvedParams = use(params)
  // Extended: holds the exam back until access checks pass (Safe Exam
  // Browser). Community builds render the interface directly.
  const ExamAccessGate = useSlot('ExamAccessGate')
  const labeling = <LabelingInterface projectId={resolvedParams.id} />
  return (
    <ProtectedRoute>
      {ExamAccessGate ? (
        // eslint-disable-next-line react-hooks/static-components
        <ExamAccessGate projectId={resolvedParams.id}>
          {labeling}
        </ExamAccessGate>
      ) : (
        labeling
      )}
    </ProtectedRoute>
  )
}
