/**
 * Hook for project management operations
 * Wraps the project store for easier component usage
 */

import { useProjectStore } from '@/stores/projectStore'
import { useCallback } from 'react'

export function useProjects() {
  const {
    projects,
    loading,
    error,
    fetchProjects: storeFetchProjects,
  } = useProjectStore()

  const fetchProjects = useCallback(async () => {
    await storeFetchProjects()
  }, [storeFetchProjects])

  return {
    projects,
    loading,
    error,
    fetchProjects,
  }
}
