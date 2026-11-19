'use client'

/**
 * Whether a project has analysis runs or variant designs, which decides
 * whether the evaluations page offers the Analyses result type. A failed
 * read (no access, no such route) counts as none.
 */

import { analysisAPI } from '@/lib/api/analysis'
import { useEffect, useState } from 'react'

export interface AnalysisAvailability {
  /** The project the answer is for (null until one is known). */
  projectId: string | null
  hasRuns: boolean
  hasDesigns: boolean
}

const NONE: AnalysisAvailability = {
  projectId: null,
  hasRuns: false,
  hasDesigns: false,
}

export function useAnalysisAvailability(
  projectId: string | null,
): AnalysisAvailability {
  const [state, setState] = useState<AnalysisAvailability>(NONE)
  useEffect(() => {
    if (!projectId) return
    let cancelled = false
    Promise.allSettled([
      analysisAPI.listRuns(projectId, 1),
      analysisAPI.listDesignKeys(projectId),
    ]).then(([runs, designs]) => {
      if (cancelled) return
      setState({
        projectId,
        hasRuns:
          runs.status === 'fulfilled' &&
          typeof runs.value?.total === 'number' &&
          runs.value.total > 0,
        hasDesigns:
          designs.status === 'fulfilled' &&
          Array.isArray(designs.value) &&
          designs.value.length > 0,
      })
    })
    return () => {
      cancelled = true
    }
  }, [projectId])
  return state.projectId === projectId ? state : NONE
}
