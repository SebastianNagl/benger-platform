'use client'

import { ModelScopeProvider } from '@/contexts/ModelScopeContext'
import { useParams } from 'next/navigation'
import type { ReactNode } from 'react'

/**
 * Every page under a project lists the models a run on THAT project can
 * use (the org whose keys the worker dispatches with), not the caller's
 * personal keys or a selected organization.
 */
export default function ProjectScopedLayout({
  children,
}: {
  children: ReactNode
}) {
  const params = useParams<{ id: string }>()
  const projectId = typeof params?.id === 'string' ? params.id : null
  return (
    <ModelScopeProvider projectId={projectId}>{children}</ModelScopeProvider>
  )
}
