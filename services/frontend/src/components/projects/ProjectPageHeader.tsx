'use client'

/**
 * The header of a page under a project: the project breadcrumb, the page
 * title in the app's standard style, an optional description, an optional
 * badge next to the title and an optional row of actions on the right.
 *
 * One place defines the title size and the spacing, so the project's pages
 * (platform and overlay alike) cannot drift apart. Render it as the first
 * child of the page's `ResponsiveContainer`; the page keeps its own width.
 */

import { ReactNode } from 'react'

import {
  ProjectBreadcrumb,
  type ProjectBreadcrumbItem,
} from '@/components/projects/ProjectBreadcrumb'

export interface ProjectPageHeaderProps {
  projectId: string
  /** The crumbs after the project; the last one is the current page. */
  breadcrumbs?: ProjectBreadcrumbItem[]
  /** The project's title when the page already has it from its own data. */
  projectTitle?: string
  title: ReactNode
  /** One line under the title. */
  description?: ReactNode
  /** Shown next to the title, such as a status chip. */
  badge?: ReactNode
  /** Buttons and links on the right of the title (below it when narrow). */
  actions?: ReactNode
  /** Further lines under the description, inside the title column. */
  children?: ReactNode
  'data-testid'?: string
}

export function ProjectPageHeader({
  projectId,
  breadcrumbs,
  projectTitle,
  title,
  description,
  badge,
  actions,
  children,
  'data-testid': testId,
}: ProjectPageHeaderProps) {
  return (
    <div className="mb-8" data-testid={testId}>
      <div className="mb-4">
        <ProjectBreadcrumb
          projectId={projectId}
          items={breadcrumbs}
          projectTitle={projectTitle}
        />
      </div>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
              {title}
            </h1>
            {badge}
          </div>
          {description && (
            <p className="mt-2 text-zinc-600 dark:text-zinc-400">
              {description}
            </p>
          )}
          {children}
        </div>
        {actions && (
          <div className="flex flex-wrap items-center gap-2">{actions}</div>
        )}
      </div>
    </div>
  )
}

export default ProjectPageHeader
