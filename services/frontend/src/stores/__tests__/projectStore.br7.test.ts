/**
 * @jest-environment jsdom
 *
 * Branch coverage round 7: projectStore.ts
 * Targets: error branches in fetchProject, createProject, updateProject, deleteProject,
 *          fetchProjectTasks, getNextTask, createAnnotation (max annotations limit),
 *          completeCurrentTask, skipTask, importData, setTaskByIndex edge cases,
 *          advanceToNextTask loop-back
 */

// Mock dependencies
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    list: jest.fn(),
    get: jest.fn(),
    create: jest.fn(),
    update: jest.fn(),
    delete: jest.fn(),
    getTasks: jest.fn(),
    getNextTask: jest.fn(),
    createAnnotation: jest.fn(),
    importData: jest.fn(),
  },
}))

jest.mock('react-hot-toast', () => ({
  toast: Object.assign(jest.fn(), {
    success: jest.fn(),
    error: jest.fn(),
  }),
}))

jest.mock('@/lib/utils/logger', () => ({
  logger: { debug: jest.fn() },
}))

jest.mock('@/lib/utils/translate', () => ({
  translate: (key: string, params?: any) => key,
}))

import { projectsAPI } from '@/lib/api/projects'
import { toast } from 'react-hot-toast'

// We need to get the store. Since it uses zustand, we can import it directly.
import { useProjectStore } from '../projectStore'

const api = projectsAPI as jest.Mocked<typeof projectsAPI>

describe('projectStore br7', () => {
  beforeEach(() => {
    // Reset the store state between tests
    useProjectStore.setState({
      projects: [],
      currentProject: null,
      currentTask: null,
      currentTaskPosition: null,
      currentTaskTotal: null,
      loading: false,
      error: null,
      searchQuery: '',
      taskCycle: [],
      currentTaskIndex: 0,
      allTasksCompleted: false,
      currentPage: 1,
      pageSize: 30,
      totalProjects: 0,
      totalPages: 0,
      labelConfigVersion: 0,
    })
    jest.clearAllMocks()
  })

  describe('fetchProject', () => {
    it('adds project to list when not already present', async () => {
      const project = { id: 'p1', title: 'Test' } as any
      api.get.mockResolvedValue(project)

      await useProjectStore.getState().fetchProject('p1')

      const state = useProjectStore.getState()
      expect(state.currentProject).toEqual(project)
      expect(state.projects).toContainEqual(project)
    })

    it('updates existing project in list', async () => {
      useProjectStore.setState({
        projects: [{ id: 'p1', title: 'Old' } as any],
      })
      const updated = { id: 'p1', title: 'New' } as any
      api.get.mockResolvedValue(updated)

      await useProjectStore.getState().fetchProject('p1')

      const state = useProjectStore.getState()
      expect(state.projects[0].title).toBe('New')
    })

    it('handles fetchProject error', async () => {
      api.get.mockRejectedValue(new Error('Not found'))

      await useProjectStore.getState().fetchProject('p1')

      const state = useProjectStore.getState()
      expect(state.error).toBe('Not found')
      expect(toast.error).toHaveBeenCalled()
    })

    it('handles fetchProject non-Error', async () => {
      api.get.mockRejectedValue('string error')

      await useProjectStore.getState().fetchProject('p1')

      const state = useProjectStore.getState()
      expect(state.error).toBe('store.project.fetchOneFailed')
    })
  })

  describe('createProject', () => {
    it('creates project successfully', async () => {
      const project = { id: 'p1', title: 'New' } as any
      api.create.mockResolvedValue(project)

      const result = await useProjectStore.getState().createProject({ title: 'New' })

      expect(result).toEqual(project)
      expect(toast.success).toHaveBeenCalled()
    })

    it('handles createProject error', async () => {
      api.create.mockRejectedValue(new Error('Validation failed'))

      await expect(
        useProjectStore.getState().createProject({ title: '' })
      ).rejects.toThrow('Validation failed')

      const state = useProjectStore.getState()
      expect(state.error).toBe('Validation failed')
    })

    it('handles createProject non-Error', async () => {
      api.create.mockRejectedValue('unknown')

      await expect(
        useProjectStore.getState().createProject({ title: '' })
      ).rejects.toBe('unknown')

      expect(useProjectStore.getState().error).toBe('store.project.createFailed')
    })
  })

  describe('updateProject', () => {
    it('updates project and increments labelConfigVersion when label_config changes', async () => {
      useProjectStore.setState({
        projects: [{ id: 'p1', title: 'Test' } as any],
        currentProject: { id: 'p1', title: 'Test' } as any,
        labelConfigVersion: 0,
      })
      api.update.mockResolvedValue({ id: 'p1', title: 'Test', label_config: '<View/>' } as any)

      await useProjectStore.getState().updateProject('p1', { label_config: '<View/>' })

      expect(useProjectStore.getState().labelConfigVersion).toBe(1)
    })

    it('does not increment labelConfigVersion for non-config updates', async () => {
      useProjectStore.setState({
        projects: [{ id: 'p1', title: 'Test' } as any],
        currentProject: { id: 'p1', title: 'Test' } as any,
        labelConfigVersion: 0,
      })
      api.update.mockResolvedValue({ id: 'p1', title: 'Updated' } as any)

      await useProjectStore.getState().updateProject('p1', { title: 'Updated' })

      expect(useProjectStore.getState().labelConfigVersion).toBe(0)
    })

    it('updates currentProject only when it matches projectId', async () => {
      useProjectStore.setState({
        projects: [{ id: 'p1', title: 'Test' } as any, { id: 'p2', title: 'Other' } as any],
        currentProject: { id: 'p2', title: 'Other' } as any,
      })
      api.update.mockResolvedValue({ id: 'p1', title: 'Updated' } as any)

      await useProjectStore.getState().updateProject('p1', { title: 'Updated' })

      // currentProject should still be p2 since we updated p1
      expect(useProjectStore.getState().currentProject?.id).toBe('p2')
    })

    it('handles updateProject error', async () => {
      api.update.mockRejectedValue(new Error('Update failed'))

      await useProjectStore.getState().updateProject('p1', { title: 'x' })

      expect(useProjectStore.getState().error).toBe('Update failed')
    })

    it('handles updateProject non-Error', async () => {
      api.update.mockRejectedValue(42)

      await useProjectStore.getState().updateProject('p1', { title: 'x' })

      expect(useProjectStore.getState().error).toBe('store.project.updateFailed')
    })
  })

  describe('deleteProject', () => {
    it('deletes and clears currentProject if it matches', async () => {
      useProjectStore.setState({
        projects: [{ id: 'p1', title: 'Test' } as any],
        currentProject: { id: 'p1', title: 'Test' } as any,
      })
      api.delete.mockResolvedValue(undefined)

      await useProjectStore.getState().deleteProject('p1')

      expect(useProjectStore.getState().currentProject).toBeNull()
      expect(useProjectStore.getState().projects).toHaveLength(0)
    })

    it('does not clear currentProject if different project deleted', async () => {
      useProjectStore.setState({
        projects: [{ id: 'p1' } as any, { id: 'p2' } as any],
        currentProject: { id: 'p2' } as any,
      })
      api.delete.mockResolvedValue(undefined)

      await useProjectStore.getState().deleteProject('p1')

      expect(useProjectStore.getState().currentProject?.id).toBe('p2')
    })

    it('handles deleteProject error', async () => {
      api.delete.mockRejectedValue(new Error('Delete failed'))

      await useProjectStore.getState().deleteProject('p1')

      expect(useProjectStore.getState().error).toBe('Delete failed')
    })

    it('handles deleteProject non-Error', async () => {
      api.delete.mockRejectedValue(null)

      await useProjectStore.getState().deleteProject('p1')

      expect(useProjectStore.getState().error).toBe('store.project.deleteFailed')
    })
  })

  describe('fetchProjectTasks', () => {
    it('fetches all tasks across multiple pages', async () => {
      const page1 = Array.from({ length: 100 }, (_, i) => ({ id: `t${i}` }))
      const page2 = [{ id: 't100' }, { id: 't101' }]
      api.getTasks.mockResolvedValueOnce(page1).mockResolvedValueOnce(page2)

      const tasks = await useProjectStore.getState().fetchProjectTasks('p1')

      expect(tasks).toHaveLength(102)
      expect(api.getTasks).toHaveBeenCalledTimes(2)
    })

    it('handles fetchProjectTasks error', async () => {
      api.getTasks.mockRejectedValue(new Error('Tasks failed'))

      const tasks = await useProjectStore.getState().fetchProjectTasks('p1')

      expect(tasks).toEqual([])
      expect(useProjectStore.getState().error).toBe('Tasks failed')
    })

    it('handles fetchProjectTasks non-Error', async () => {
      api.getTasks.mockRejectedValue(undefined)

      const tasks = await useProjectStore.getState().fetchProjectTasks('p1')

      expect(tasks).toEqual([])
      expect(useProjectStore.getState().error).toBe('store.project.fetchTasksFailed')
    })
  })

  describe('setTaskByIndex', () => {
    it('sets task when valid index', () => {
      useProjectStore.setState({
        taskCycle: [{ id: 't1' } as any, { id: 't2' } as any],
      })

      useProjectStore.getState().setTaskByIndex(1)

      expect(useProjectStore.getState().currentTask?.id).toBe('t2')
      expect(useProjectStore.getState().currentTaskPosition).toBe(2)
    })

    it('warns for invalid index', () => {
      const warnSpy = jest.spyOn(console, 'warn').mockImplementation()
      useProjectStore.setState({ taskCycle: [{ id: 't1' } as any] })

      useProjectStore.getState().setTaskByIndex(5)

      expect(warnSpy).toHaveBeenCalled()
      warnSpy.mockRestore()
    })

    it('warns for negative index', () => {
      const warnSpy = jest.spyOn(console, 'warn').mockImplementation()
      useProjectStore.setState({ taskCycle: [{ id: 't1' } as any] })

      useProjectStore.getState().setTaskByIndex(-1)

      expect(warnSpy).toHaveBeenCalled()
      warnSpy.mockRestore()
    })
  })

  describe('advanceToNextTask', () => {
    it('advances to next task', () => {
      useProjectStore.setState({
        taskCycle: [{ id: 't1' } as any, { id: 't2' } as any],
        currentTaskIndex: 0,
      })

      useProjectStore.getState().advanceToNextTask()

      expect(useProjectStore.getState().currentTaskIndex).toBe(1)
      expect(useProjectStore.getState().currentTask?.id).toBe('t2')
    })

    it('loops back to beginning and shows toast', () => {
      useProjectStore.setState({
        taskCycle: [{ id: 't1' } as any, { id: 't2' } as any],
        currentTaskIndex: 1,
      })

      useProjectStore.getState().advanceToNextTask()

      expect(useProjectStore.getState().currentTaskIndex).toBe(0)
      expect(toast).toHaveBeenCalled()
    })

    it('does nothing when taskCycle is empty', () => {
      useProjectStore.setState({ taskCycle: [], currentTaskIndex: 0 })

      useProjectStore.getState().advanceToNextTask()

      expect(useProjectStore.getState().currentTaskIndex).toBe(0)
    })
  })

  describe('completeCurrentTask', () => {
    it('removes task and advances in open mode', async () => {
      useProjectStore.setState({
        currentProject: { id: 'p1', assignment_mode: 'open' } as any,
        taskCycle: [{ id: 't1' } as any, { id: 't2' } as any],
        currentTaskIndex: 0,
      })

      await useProjectStore.getState().completeCurrentTask()

      expect(useProjectStore.getState().taskCycle).toHaveLength(1)
      expect(useProjectStore.getState().currentTask?.id).toBe('t2')
    })

    it('sets allTasksCompleted when last task completed in open mode', async () => {
      useProjectStore.setState({
        currentProject: { id: 'p1', assignment_mode: 'open' } as any,
        taskCycle: [{ id: 't1' } as any],
        currentTaskIndex: 0,
      })

      await useProjectStore.getState().completeCurrentTask()

      expect(useProjectStore.getState().allTasksCompleted).toBe(true)
      expect(useProjectStore.getState().taskCycle).toHaveLength(0)
    })

    it('handles auto mode by fetching next task', async () => {
      useProjectStore.setState({
        currentProject: { id: 'p1', assignment_mode: 'auto' } as any,
        taskCycle: [],
        currentTaskIndex: 0,
      })
      api.getNextTask.mockResolvedValue({ task: { id: 't2' }, current_position: 1, total_tasks: 5 })

      await useProjectStore.getState().completeCurrentTask()

      expect(api.getNextTask).toHaveBeenCalledWith('p1')
    })

    it('sets allTasksCompleted in auto mode when no next task', async () => {
      useProjectStore.setState({
        currentProject: { id: 'p1', assignment_mode: 'auto' } as any,
        taskCycle: [],
        currentTaskIndex: 0,
      })
      api.getNextTask.mockResolvedValue({ task: null })

      await useProjectStore.getState().completeCurrentTask()

      expect(useProjectStore.getState().allTasksCompleted).toBe(true)
    })

    it('wraps index when currentTaskIndex exceeds updated cycle length', async () => {
      useProjectStore.setState({
        currentProject: { id: 'p1', assignment_mode: 'open' } as any,
        taskCycle: [{ id: 't1' } as any, { id: 't2' } as any],
        currentTaskIndex: 1,  // Last index, removing it should wrap to 0
      })

      await useProjectStore.getState().completeCurrentTask()

      expect(useProjectStore.getState().currentTaskIndex).toBe(0)
    })
  })

  describe('importData', () => {
    it('imports data and refreshes current project', async () => {
      useProjectStore.setState({
        currentProject: { id: 'p1' } as any,
      })
      api.importData.mockResolvedValue({ created: 5 })
      api.get.mockResolvedValue({ id: 'p1', task_count: 5 } as any)

      await useProjectStore.getState().importData('p1', [{ text: 'test' }])

      expect(api.importData).toHaveBeenCalledWith('p1', { data: [{ text: 'test' }] })
      expect(toast.success).toHaveBeenCalled()
      // Should refetch the project since it's the current one
      expect(api.get).toHaveBeenCalledWith('p1')
    })

    it('refreshes projects list when importing to non-current project', async () => {
      useProjectStore.setState({
        currentProject: { id: 'p2' } as any,
      })
      api.importData.mockResolvedValue({ created: 3 })
      api.list.mockResolvedValue({ items: [], total: 0, pages: 1 })

      await useProjectStore.getState().importData('p1', [{ text: 'test' }])

      expect(api.list).toHaveBeenCalled()
    })

    it('handles importData error', async () => {
      api.importData.mockRejectedValue(new Error('Import failed'))

      await useProjectStore.getState().importData('p1', [])

      expect(useProjectStore.getState().error).toBe('Import failed')
    })

    it('handles importData non-Error', async () => {
      api.importData.mockRejectedValue(false)

      await useProjectStore.getState().importData('p1', [])

      expect(useProjectStore.getState().error).toBe('store.project.importFailed')
    })
  })

  describe('selectProject', () => {
    it('selects existing project from list', () => {
      useProjectStore.setState({
        projects: [{ id: 'p1', title: 'Test' } as any],
      })

      useProjectStore.getState().selectProject('p1')

      expect(useProjectStore.getState().currentProject?.id).toBe('p1')
    })

    it('sets null when project not found', () => {
      useProjectStore.setState({ projects: [] })

      useProjectStore.getState().selectProject('unknown')

      expect(useProjectStore.getState().currentProject).toBeNull()
    })
  })

  describe('UI actions', () => {
    it('setSearchQuery resets to page 1', () => {
      useProjectStore.setState({ currentPage: 3 })

      useProjectStore.getState().setSearchQuery('test')

      expect(useProjectStore.getState().searchQuery).toBe('test')
      expect(useProjectStore.getState().currentPage).toBe(1)
    })

    it('setPageSize resets to page 1 and fetches', () => {
      api.list.mockResolvedValue({ items: [], total: 0, pages: 1 })
      useProjectStore.setState({ currentPage: 3 })

      useProjectStore.getState().setPageSize(50)

      expect(useProjectStore.getState().pageSize).toBe(50)
      expect(useProjectStore.getState().currentPage).toBe(1)
    })

    it('clearError clears error', () => {
      useProjectStore.setState({ error: 'Something' })

      useProjectStore.getState().clearError()

      expect(useProjectStore.getState().error).toBeNull()
    })

    it('resetAnnotationCompletion resets flag', () => {
      useProjectStore.setState({ allTasksCompleted: true })

      useProjectStore.getState().resetAnnotationCompletion()

      expect(useProjectStore.getState().allTasksCompleted).toBe(false)
    })
  })

  describe('fetchProjects', () => {
    it('handles missing response fields gracefully', async () => {
      api.list.mockResolvedValue({} as any)

      await useProjectStore.getState().fetchProjects()

      const state = useProjectStore.getState()
      expect(state.projects).toEqual([])
      expect(state.totalProjects).toBe(0)
      expect(state.totalPages).toBe(1)
    })

    it('handles fetchProjects error', async () => {
      api.list.mockRejectedValue(new Error('Network error'))

      await useProjectStore.getState().fetchProjects()

      expect(useProjectStore.getState().error).toBe('Network error')
      expect(useProjectStore.getState().projects).toEqual([])
    })

    it('handles fetchProjects non-Error', async () => {
      api.list.mockRejectedValue(undefined)

      await useProjectStore.getState().fetchProjects()

      expect(useProjectStore.getState().error).toBe('store.project.fetchFailed')
    })

    it('handles non-array projects in response', async () => {
      api.list.mockResolvedValue({ items: 'not-an-array', total: 0, pages: 1 } as any)

      await useProjectStore.getState().fetchProjects()

      expect(useProjectStore.getState().projects).toEqual([])
    })
  })

  describe('createAnnotationInternal', () => {
    it('auto-advances after annotation in open mode', async () => {
      useProjectStore.setState({
        currentProject: { id: 'p1', assignment_mode: 'open' } as any,
        taskCycle: [{ id: 't1' } as any, { id: 't2' } as any],
        currentTaskIndex: 0,
      })
      api.createAnnotation.mockResolvedValue({ id: 'a1' } as any)

      const result = await useProjectStore.getState().createAnnotationInternal('t1', { result: [] })

      expect(result).toEqual({ id: 'a1' })
      // Task should have been removed from cycle
      expect(useProjectStore.getState().taskCycle).toHaveLength(1)
    })

    it('sets allTasksCompleted when last task annotated in open mode', async () => {
      useProjectStore.setState({
        currentProject: { id: 'p1', assignment_mode: 'open' } as any,
        taskCycle: [{ id: 't1' } as any],
        currentTaskIndex: 0,
      })
      api.createAnnotation.mockResolvedValue({ id: 'a1' } as any)

      await useProjectStore.getState().createAnnotationInternal('t1', { result: [] })

      expect(useProjectStore.getState().allTasksCompleted).toBe(true)
    })

    it('skips auto-advance when skipAdvance is true', async () => {
      useProjectStore.setState({
        currentProject: { id: 'p1', assignment_mode: 'open' } as any,
        taskCycle: [{ id: 't1' } as any, { id: 't2' } as any],
        currentTaskIndex: 0,
      })
      api.createAnnotation.mockResolvedValue({ id: 'a1' } as any)

      await useProjectStore.getState().createAnnotationInternal('t1', { result: [] }, true)

      // Task cycle should NOT have changed
      expect(useProjectStore.getState().taskCycle).toHaveLength(2)
    })

    it('auto-advances in auto mode by fetching next task', async () => {
      useProjectStore.setState({
        currentProject: { id: 'p1', assignment_mode: 'auto' } as any,
        taskCycle: [],
        currentTaskIndex: 0,
      })
      api.createAnnotation.mockResolvedValue({ id: 'a1' } as any)
      api.getNextTask.mockResolvedValue({ task: { id: 't2' }, current_position: 1, total_tasks: 5 })

      await useProjectStore.getState().createAnnotationInternal('t1', { result: [] })

      expect(api.getNextTask).toHaveBeenCalledWith('p1')
    })

    it('throws on createAnnotation error', async () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
      api.createAnnotation.mockRejectedValue(new Error('Create failed'))

      await expect(
        useProjectStore.getState().createAnnotationInternal('t1', {})
      ).rejects.toThrow('Create failed')

      consoleSpy.mockRestore()
    })
  })
})
