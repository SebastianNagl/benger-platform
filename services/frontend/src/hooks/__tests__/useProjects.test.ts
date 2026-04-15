/**
 * @jest-environment jsdom
 */

/**
 * Comprehensive tests for useProjects hook
 * Tests hook behavior, data fetching, loading states, errors, and CRUD operations
 */

import { useProjectStore } from '@/stores/projectStore'
import { act, renderHook } from '@testing-library/react'
import React from 'react'
import { useProjects } from '../useProjects'

// Mock dependencies
jest.mock('react-hot-toast')
jest.mock('@/lib/api/projects')
jest.mock('@/stores/projectStore')

// Mock project data
const mockProject1 = {
  id: 'project-1',
  title: 'Test Project 1',
  description: 'First test project',
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
  task_count: 10,
  annotation_count: 5,
  is_published: false,
  is_archived: false,
  label_config: '<View></View>',
}

const mockProject2 = {
  id: 'project-2',
  title: 'Test Project 2',
  description: 'Second test project',
  created_at: '2025-01-02T00:00:00Z',
  updated_at: '2025-01-02T00:00:00Z',
  task_count: 20,
  annotation_count: 15,
  is_published: true,
  is_archived: false,
  label_config: '<View></View>',
}

const mockArchivedProject = {
  id: 'project-3',
  title: 'Archived Project',
  description: 'Archived test project',
  created_at: '2025-01-03T00:00:00Z',
  updated_at: '2025-01-03T00:00:00Z',
  task_count: 5,
  annotation_count: 5,
  is_published: false,
  is_archived: true,
  label_config: '<View></View>',
}

// Simple wrapper for hook testing
const wrapper = ({ children }: { children: React.ReactNode }) =>
  children as React.ReactElement

describe('useProjects Hook', () => {
  let mockFetchProjects: jest.Mock

  beforeEach(() => {
    jest.clearAllMocks()

    // Create mock function
    mockFetchProjects = jest.fn().mockResolvedValue(undefined)

    // Setup default mock implementation
    ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
      projects: [],
      loading: false,
      error: null,
      fetchProjects: mockFetchProjects,
    })
  })

  describe('1. Basic Hook Behavior', () => {
    it('should return initial state with empty projects', () => {
      const { result } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.projects).toEqual([])
      expect(result.current.loading).toBe(false)
      expect(result.current.error).toBeNull()
      expect(result.current.fetchProjects).toBeDefined()
      expect(typeof result.current.fetchProjects).toBe('function')
    })

    it('should expose fetchProjects function from store', () => {
      const { result } = renderHook(() => useProjects(), { wrapper })

      // fetchProjects is wrapped in useCallback, so check it's a function
      expect(typeof result.current.fetchProjects).toBe('function')
      expect(result.current.fetchProjects).toBeDefined()
    })

    it('should return stable references across re-renders', () => {
      const { result, rerender } = renderHook(() => useProjects(), { wrapper })

      const firstFetchProjects = result.current.fetchProjects

      rerender()

      expect(result.current.fetchProjects).toBe(firstFetchProjects)
    })

    it('should update when store state changes', () => {
      const { result, rerender } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.projects).toEqual([])

      // Update mock to return projects
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [mockProject1],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      rerender()

      expect(result.current.projects).toEqual([mockProject1])
    })
  })

  describe('2. Projects Data Fetching', () => {
    it('should call fetchProjects from store', async () => {
      const { result } = renderHook(() => useProjects(), { wrapper })

      await act(async () => {
        await result.current.fetchProjects()
      })

      expect(mockFetchProjects).toHaveBeenCalledTimes(1)
    })

    it('should return projects after successful fetch', async () => {
      // Initially empty
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [],
        loading: true,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      const { result, rerender } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.projects).toEqual([])
      expect(result.current.loading).toBe(true)

      // Simulate successful fetch
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [mockProject1, mockProject2],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      rerender()

      expect(result.current.projects).toHaveLength(2)
      expect(result.current.projects[0]).toEqual(mockProject1)
      expect(result.current.projects[1]).toEqual(mockProject2)
      expect(result.current.loading).toBe(false)
    })

    it('should handle multiple projects with different statuses', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [mockProject1, mockProject2, mockArchivedProject],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      const { result } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.projects).toHaveLength(3)
      expect(result.current.projects.filter((p) => p.is_archived)).toHaveLength(
        1
      )
      expect(
        result.current.projects.filter((p) => !p.is_archived)
      ).toHaveLength(2)
      expect(
        result.current.projects.filter((p) => p.is_published)
      ).toHaveLength(1)
    })

    it('should preserve project metadata', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [mockProject1],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      const { result } = renderHook(() => useProjects(), { wrapper })

      const project = result.current.projects[0]
      expect(project.id).toBe('project-1')
      expect(project.title).toBe('Test Project 1')
      expect(project.description).toBe('First test project')
      expect(project.task_count).toBe(10)
      expect(project.annotation_count).toBe(5)
      expect(project.label_config).toBe('<View></View>')
    })
  })

  describe('3. Loading States', () => {
    it('should reflect loading state from store', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [],
        loading: true,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      const { result } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.loading).toBe(true)
    })

    it('should update loading state during fetch', async () => {
      // Start with loading false
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      const { result, rerender } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.loading).toBe(false)

      // Simulate fetch starting - loading becomes true
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [],
        loading: true,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      rerender()

      expect(result.current.loading).toBe(true)

      // Simulate fetch complete - loading becomes false
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [mockProject1],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      rerender()

      expect(result.current.loading).toBe(false)
    })

    it('should set loading to false after successful fetch', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [mockProject1, mockProject2],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      const { result } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.loading).toBe(false)
      expect(result.current.projects).toHaveLength(2)
    })

    it('should set loading to false after failed fetch', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [],
        loading: false,
        error: 'Failed to fetch projects',
        fetchProjects: mockFetchProjects,
      })

      const { result } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.loading).toBe(false)
      expect(result.current.error).toBe('Failed to fetch projects')
    })
  })

  describe('4. Error Handling', () => {
    it('should handle fetch errors', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [],
        loading: false,
        error: 'Network error occurred',
        fetchProjects: mockFetchProjects,
      })

      const { result } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.error).toBe('Network error occurred')
      expect(result.current.projects).toEqual([])
    })

    it('should handle API error responses', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [],
        loading: false,
        error: 'Failed to fetch projects',
        fetchProjects: mockFetchProjects,
      })

      const { result } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.error).toBe('Failed to fetch projects')
    })

    it('should clear error on successful fetch', () => {
      // Start with error
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [],
        loading: false,
        error: 'Previous error',
        fetchProjects: mockFetchProjects,
      })

      const { result, rerender } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.error).toBe('Previous error')

      // Successful fetch clears error
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [mockProject1],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      rerender()

      expect(result.current.error).toBeNull()
      expect(result.current.projects).toHaveLength(1)
    })

    it('should handle authentication errors', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [],
        loading: false,
        error: 'Unauthorized',
        fetchProjects: mockFetchProjects,
      })

      const { result } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.error).toBe('Unauthorized')
    })

    it('should handle timeout errors', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [],
        loading: false,
        error: 'Request timeout',
        fetchProjects: mockFetchProjects,
      })

      const { result } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.error).toBe('Request timeout')
    })
  })

  describe('5. Filtering and Sorting', () => {
    it('should return all non-archived projects by default', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [mockProject1, mockProject2],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      const { result } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.projects).toHaveLength(2)
      expect(result.current.projects.every((p) => !p.is_archived)).toBe(true)
    })

    it('should include archived projects when present', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [mockProject1, mockArchivedProject],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      const { result } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.projects).toHaveLength(2)
      const archived = result.current.projects.find((p) => p.is_archived)
      expect(archived).toBeDefined()
      expect(archived?.id).toBe('project-3')
    })

    it('should maintain project order from store', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [mockProject2, mockProject1],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      const { result } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.projects[0].id).toBe('project-2')
      expect(result.current.projects[1].id).toBe('project-1')
    })

    it('should handle empty project list', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      const { result } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.projects).toEqual([])
      expect(Array.isArray(result.current.projects)).toBe(true)
    })
  })

  describe('6. CRUD Operations', () => {
    it('should reflect newly created projects', () => {
      // Initially empty
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      const { result, rerender } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.projects).toEqual([])

      // After create
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [mockProject1],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      rerender()

      expect(result.current.projects).toHaveLength(1)
      expect(result.current.projects[0]).toEqual(mockProject1)
    })

    it('should reflect updated project data', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [mockProject1],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      const { result, rerender } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.projects[0].title).toBe('Test Project 1')

      // After update
      const updatedProject = { ...mockProject1, title: 'Updated Title' }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [updatedProject],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      rerender()

      expect(result.current.projects[0].title).toBe('Updated Title')
    })

    it('should reflect archived projects', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [mockProject1],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      const { result, rerender } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.projects[0].is_archived).toBe(false)

      // After archive
      const archivedProject = { ...mockProject1, is_archived: true }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [archivedProject],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      rerender()

      expect(result.current.projects[0].is_archived).toBe(true)
    })

    it('should reflect deleted projects', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [mockProject1, mockProject2],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      const { result, rerender } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.projects).toHaveLength(2)

      // After delete
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [mockProject1],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      rerender()

      expect(result.current.projects).toHaveLength(1)
      expect(result.current.projects[0].id).toBe('project-1')
    })
  })

  describe('7. Edge Cases', () => {
    it('should handle undefined projects gracefully', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: undefined,
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      const { result } = renderHook(() => useProjects(), { wrapper })

      // Hook should handle undefined gracefully
      expect(result.current.projects).toBeUndefined()
    })

    it('should handle null projects', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: null,
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      const { result } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.projects).toBeNull()
    })

    it('should handle projects with missing optional fields', () => {
      const minimalProject = {
        id: 'minimal-1',
        title: 'Minimal Project',
        created_at: '2025-01-01T00:00:00Z',
        updated_at: '2025-01-01T00:00:00Z',
        is_published: false,
        is_archived: false,
      }

      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [minimalProject],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      const { result } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.projects).toHaveLength(1)
      expect(result.current.projects[0].id).toBe('minimal-1')
    })

    it('should handle very large project lists', () => {
      const manyProjects = Array.from({ length: 1000 }, (_, i) => ({
        ...mockProject1,
        id: `project-${i}`,
        title: `Project ${i}`,
      }))

      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: manyProjects,
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      const { result } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.projects).toHaveLength(1000)
    })

    it('should handle projects with special characters in titles', () => {
      const specialProject = {
        ...mockProject1,
        title: 'Test <>&" Project\n\t\r',
        description: 'Project with \'quotes\' and "double quotes"',
      }

      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [specialProject],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      const { result } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.projects[0].title).toBe('Test <>&" Project\n\t\r')
    })

    it('should handle rapid state changes', () => {
      const { result, rerender } = renderHook(() => useProjects(), { wrapper })

      // Rapidly change state
      for (let i = 0; i < 10; i++) {
        ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
          projects: Array.from({ length: i }, (_, j) => ({
            ...mockProject1,
            id: `project-${j}`,
          })),
          loading: i % 2 === 0,
          error: i % 3 === 0 ? 'Error' : null,
          fetchProjects: mockFetchProjects,
        })

        rerender()
      }

      // Should handle without crashes
      expect(result.current).toBeDefined()
    })

    it('should handle concurrent fetches', async () => {
      const { result } = renderHook(() => useProjects(), { wrapper })

      // Trigger multiple fetches simultaneously
      const promises = [
        result.current.fetchProjects(),
        result.current.fetchProjects(),
        result.current.fetchProjects(),
      ]

      await act(async () => {
        await Promise.all(promises)
      })

      // All should call the same store function
      expect(mockFetchProjects).toHaveBeenCalledTimes(3)
    })
  })

  describe('8. API Integration', () => {
    it('should call store fetchProjects with no arguments', async () => {
      const { result } = renderHook(() => useProjects(), { wrapper })

      await act(async () => {
        await result.current.fetchProjects()
      })

      expect(mockFetchProjects).toHaveBeenCalledWith()
    })

    it('should handle successful API responses', async () => {
      mockFetchProjects.mockResolvedValueOnce(undefined)
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      const { result, rerender } = renderHook(() => useProjects(), { wrapper })

      await act(async () => {
        await result.current.fetchProjects()
      })

      // After successful fetch
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [mockProject1, mockProject2],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      rerender()

      expect(result.current.projects).toHaveLength(2)
      expect(result.current.error).toBeNull()
    })

    it('should handle API failures', async () => {
      mockFetchProjects.mockRejectedValueOnce(new Error('API Error'))

      const { result } = renderHook(() => useProjects(), { wrapper })

      await act(async () => {
        try {
          await result.current.fetchProjects()
        } catch (error) {
          // Error should be caught
        }
      })

      expect(mockFetchProjects).toHaveBeenCalled()
    })

    it('should handle network timeouts', async () => {
      mockFetchProjects.mockImplementationOnce(
        () =>
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error('Timeout')), 100)
          )
      )

      const { result } = renderHook(() => useProjects(), { wrapper })

      await act(async () => {
        try {
          await result.current.fetchProjects()
        } catch (error) {
          expect((error as Error).message).toBe('Timeout')
        }
      })
    })

    it('should maintain consistency between hook and store', () => {
      const storeState = {
        projects: [mockProject1, mockProject2],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      }

      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(storeState)

      const { result } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.projects).toBe(storeState.projects)
      expect(result.current.loading).toBe(storeState.loading)
      expect(result.current.error).toBe(storeState.error)
      // fetchProjects is wrapped in useCallback, so just check it exists
      expect(typeof result.current.fetchProjects).toBe('function')
    })

    it('should handle empty API responses', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      const { result } = renderHook(() => useProjects(), { wrapper })

      expect(result.current.projects).toEqual([])
      expect(result.current.loading).toBe(false)
      expect(result.current.error).toBeNull()
    })

    it('should expose memoized fetchProjects callback', () => {
      const { result, rerender } = renderHook(() => useProjects(), { wrapper })

      const firstCallback = result.current.fetchProjects

      // Rerender without changing store
      rerender()

      // Callback should be the same reference
      expect(result.current.fetchProjects).toBe(firstCallback)
    })

    it('should update callback when store fetchProjects changes', () => {
      const mockFetch1 = jest.fn()
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [],
        loading: false,
        error: null,
        fetchProjects: mockFetch1,
      })

      const { result, rerender } = renderHook(() => useProjects(), { wrapper })

      const firstCallback = result.current.fetchProjects
      expect(typeof firstCallback).toBe('function')

      // Change store's fetchProjects
      const mockFetch2 = jest.fn()
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        projects: [],
        loading: false,
        error: null,
        fetchProjects: mockFetch2,
      })

      rerender()

      // Callback should change when store's fetchProjects changes (useCallback dependency)
      expect(result.current.fetchProjects).not.toBe(firstCallback)
      expect(typeof result.current.fetchProjects).toBe('function')
    })
  })
})
