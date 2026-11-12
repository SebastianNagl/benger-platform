'use client'

import { DeletedProjectBanner } from '@/components/projects/DeletedProjectBanner'
import { ModelScopeProvider } from '@/contexts/ModelScopeContext'
import { useParams } from 'next/navigation'
import type { ReactNode } from 'react'

/**
 * Every page under a project lists the models a run on THAT project can
 * use (the org whose keys the worker dispatches with), not the caller's
 * personal keys or a selected organization. A soft-deleted project (only
 * superadmins can open one) carries the deleted banner on every page.
 */
export default function ProjectScopedLayout({
  children,
}: {
  children: ReactNode
}) {
  const params = useParams<{ id: string }>()
  const projectId = typeof params?.id === 'string' ? params.id : null
  return (
    <ModelScopeProvider projectId={projectId}>
      <DeletedProjectBanner projectId={projectId} />
      {children}
    </ModelScopeProvider>
  )
}
