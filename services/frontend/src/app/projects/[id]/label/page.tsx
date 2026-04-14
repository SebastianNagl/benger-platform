/**
 * Labeling page - Label Studio aligned annotation interface
 *
 * This page provides the single-task annotation interface with keyboard shortcuts
 */

'use client'

import { ProtectedRoute } from '@/components/auth/ProtectedRoute'
import { LabelingInterface } from '@/components/labeling/LabelingInterface'
import { use } from 'react'

interface LabelingPageProps {
  params: Promise<{
    id: string
  }>
}

export default function LabelingPage({ params }: LabelingPageProps) {
  const resolvedParams = use(params)
  return (
    <ProtectedRoute>
      <LabelingInterface projectId={resolvedParams.id} />
    </ProtectedRoute>
  )
}
