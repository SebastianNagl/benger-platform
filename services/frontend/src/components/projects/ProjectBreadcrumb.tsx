'use client'

/**
 * The breadcrumb trail of every page under a project: dashboard, projects,
 * the project (by its title), then the page's own crumbs. One component, so
 * every project page leads back the same way instead of carrying its own
 * hand-written trail or a "back to the project" button.
 *
 * The project's title comes from the project store, and only when the store
 * holds this very project: a page opened while the store still holds
 * another one (a link, the browser history, a second tab) reads the project
 * and shows its id until then, never the other project's title. A page that
 * already knows the title from its own data passes `projectTitle`, and the
 * store is then neither read nor fetched.
 */

import { useEffect } from 'react'

import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { useI18n } from '@/contexts/I18nContext'
import { useProjectStore } from '@/stores/projectStore'

export interface ProjectBreadcrumbItem {
  label: string
  href?: string
}

export interface ProjectBreadcrumbProps {
  projectId: string
  /** The crumbs after the project; the last one is the current page. */
  items?: ProjectBreadcrumbItem[]
  /** The project's title when the page already has it from its own data. */
  projectTitle?: string
}

export function ProjectBreadcrumb({
  projectId,
  items = [],
  projectTitle,
}: ProjectBreadcrumbProps) {
  const { t } = useI18n()
  const { currentProject, fetchProject } = useProjectStore()
  const storeTitle =
    currentProject && String(currentProject.id) === String(projectId)
      ? currentProject.title
      : undefined
  const needsFetch = projectTitle === undefined && storeTitle === undefined

  useEffect(() => {
    if (projectId && needsFetch) void fetchProject(projectId, { shared: true })
  }, [projectId, needsFetch, fetchProject])

  return (
    <Breadcrumb
      items={[
        { label: t('navigation.dashboard'), href: '/dashboard' },
        { label: t('navigation.projects'), href: '/projects' },
        {
          label: projectTitle || storeTitle || projectId,
          href: `/projects/${projectId}`,
        },
        ...items,
      ]}
    />
  )
}

export default ProjectBreadcrumb
