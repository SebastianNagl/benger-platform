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
 * and shows a title-sized placeholder until then, never the other project's
 * title and not its id (a long id wraps the trail onto a second line, which
 * the title then takes back). The id stands in only when the read fails. A
 * page that already knows the title from its own data passes
 * `projectTitle`, and the store is then neither read nor fetched.
 */

import { useEffect, useState } from 'react'

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
  const [failedId, setFailedId] = useState<string | null>(null)

  useEffect(() => {
    if (!projectId || !needsFetch) return
    let cancelled = false
    Promise.resolve(fetchProject(projectId, { shared: true })).then(
      (project) => {
        if (!cancelled && project === null) setFailedId(projectId)
      },
    )
    return () => {
      cancelled = true
    }
  }, [projectId, needsFetch, fetchProject])

  const title = projectTitle || storeTitle
  const projectLabel =
    title ||
    (failedId === projectId ? (
      projectId
    ) : (
      <span data-testid="project-breadcrumb-pending">
        <span
          aria-hidden="true"
          className="inline-block h-3.5 w-28 animate-pulse rounded bg-zinc-200 align-middle dark:bg-zinc-700"
        />
        <span className="sr-only">{t('project.loading')}</span>
      </span>
    ))

  return (
    <Breadcrumb
      items={[
        { label: t('navigation.dashboard'), href: '/dashboard' },
        { label: t('navigation.projects'), href: '/projects' },
        {
          label: projectLabel,
          href: `/projects/${projectId}`,
        },
        ...items,
      ]}
    />
  )
}

export default ProjectBreadcrumb
