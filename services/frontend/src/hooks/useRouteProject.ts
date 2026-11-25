'use client'

import { useEffect, useState } from 'react'

import { useProjectStore } from '@/stores/projectStore'
import type { Project } from '@/types/labelStudio'

export interface RouteProject {
  /**
   * The store's project when it is the one this route names, else null. The
   * store keeps the last project any page loaded; showing that one under
   * another project's URL would render its title, gates and quick actions
   * until the right answer replaces them.
   */
  project: Project | null
  /** The API refused the project (404/403): show "not found". */
  notFound: boolean
}

/**
 * The project a `/projects/[id]/...` page is about, loaded through the
 * shared project store.
 *
 * Fetches when the store does not hold this project. With `refresh`, it
 * fetches once per project id even when the store holds it (the project
 * page wants fresh counts on every visit) and shows the held copy
 * meanwhile, since it is the same project. "Not found" only follows an
 * answer, never the frames before the first request has started.
 */
export function useRouteProject(
  projectId: string | null | undefined,
  { refresh = false }: { refresh?: boolean } = {},
): RouteProject {
  const { currentProject, fetchProject } = useProjectStore()
  const project =
    projectId && currentProject && String(currentProject.id) === projectId
      ? currentProject
      : null
  const [failedId, setFailedId] = useState<string | null>(null)

  const held = project !== null
  // With refresh, only a new id refetches; without, also losing the
  // project to another page's load does.
  const fetchKey = refresh || held
  useEffect(() => {
    if (!projectId || (fetchKey && !refresh)) return
    let cancelled = false
    // fetchProject resolves to null when the API refused the project.
    Promise.resolve(fetchProject(projectId, { shared: true })).then(
      (loaded) => {
        if (!cancelled) setFailedId(loaded === null ? projectId : null)
      },
    )
    return () => {
      cancelled = true
    }
  }, [projectId, fetchKey, refresh, fetchProject])

  return {
    project,
    notFound: !project && projectId != null && failedId === projectId,
  }
}
