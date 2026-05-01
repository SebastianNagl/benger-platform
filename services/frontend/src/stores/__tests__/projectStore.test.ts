/**
 * @jest-environment jsdom
 */

import { projectsAPI } from '@/lib/api/projects'
import { Annotation, Project, Task } from '@/types/labelStudio'
import { act } from '@testing-library/react'
import { mockToast as mockToastSetup } from '@/test-utils/setupTests'
import { useProjectStore } from '../projectStore'

// projectStore now calls module-level toast(msg, type) from @/components/shared/Toast.
// The setupTests global mock dispatches toast() to per-type mocks. Alias them
// under the legacy `toast.success`/`toast.error` shape so existing assertions
// keep working without rewriting every call site.
const toast = { success: mockToastSetup.success, error: mockToastSetup.error }

// Mock dependencies
jest.mock('@/lib/api/projects')

// Mock translate to return the key (with variable interpolation on the key string)
jest.mock('@/lib/utils/translate', () => ({
  translate: (key: string, vars?: Record<string, any>) => {
    if (vars) {
      return key.replace(/\{(\w+)\}/g, (_, name) =>
        vars[name] !== undefined ? String(vars[name]) : `{${name}}`
      )
    }
    return key
  },
}))

// Mock i18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => key,
    currentLanguage: 'en',
  }),
}))

// Create stable mock functions
const mockProjectsAPI = projectsAPI as jest.Mocked<typeof projectsAPI>
const mockToast = toast as jest.Mocked<typeof toast>

// Helper to create mock projects
const createMockProject = (overrides?: Partial<Project>): Project => ({
  id: '1',
  title: 'Test Project',
  description: 'Test Description',
  created_by: 'user1',
  created_by_name: 'Test User',
  organization_id: 'org1',
  label_config: '<View></View>',
  show_instruction: false,
  show_skip_button: true,
  show_submit_button: true,
  require_comment_on_skip: false,
  require_confirm_before_submit: false,
  enable_empty_annotation: false,
  maximum_annotations: 1,
  min_annotations_to_start_training: 10,
  num_tasks: 10,
  num_annotations: 5,
  is_published: false,
  is_archived: false,
  created_at: '2025-01-01T00:00:00Z',
  ...overrides,
})

// Helper to create mock tasks
const createMockTask = (overrides?: Partial<Task>): Task => ({
  id: '1',
  project_id: '1',
  data: { text: 'Test task' },
  is_labeled: false,
  total_annotations: 0,
  cancelled_annotations: 0,
  total_predictions: 0,
  created_at: '2025-01-01T00:00:00Z',
  ...overrides,
})

// Helper to create mock annotations
const createMockAnnotation = (overrides?: Partial<Annotation>): Annotation => ({
  id: '1',
  task_id: 1,
  project_id: '1',
  completed_by: 'user1',
  result: [],
  was_cancelled: false,
  ground_truth: false,
  created_at: '2025-01-01T00:00:00Z',
  ...overrides,
})

describe('ProjectStore', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    // Reset store to initial state
    act(() => {
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
        currentPage: 1,
        pageSize: 30,
        totalProjects: 0,
        totalPages: 0,
        labelConfigVersion: 0,
      })
    })
  })

  describe('Store Initialization', () => {
    it('should initialize with correct default state', () => {
      const state = useProjectStore.getState()

      expect(state.projects).toEqual([])
      expect(state.currentProject).toBeNull()
      expect(state.currentTask).toBeNull()
      expect(state.currentTaskPosition).toBeNull()
      expect(state.currentTaskTotal).toBeNull()
      expect(state.loading).toBe(false)
      expect(state.error).toBeNull()
      expect(state.searchQuery).toBe('')
      expect(state.taskCycle).toEqual([])
      expect(state.currentTaskIndex).toBe(0)
      expect(state.currentPage).toBe(1)
      expect(state.pageSize).toBe(30)
      expect(state.totalProjects).toBe(0)
      expect(state.totalPages).toBe(0)
      expect(state.labelConfigVersion).toBe(0)
    })
  })

  describe('fetchProjects', () => {
    it('should fetch projects successfully', async () => {
      const mockProjects = [
        createMockProject({ id: '1', title: 'Project 1' }),
        createMockProject({ id: '2', title: 'Project 2' }),
      ]

      mockProjectsAPI.list.mockResolvedValue({
        items: mockProjects,
        total: 2,
        page: 1,
        page_size: 30,
        pages: 1,
      })

      await act(async () => {
        await useProjectStore.getState().fetchProjects()
      })

      const state = useProjectStore.getState()
      expect(state.projects).toEqual(mockProjects)
      expect(state.totalProjects).toBe(2)
      expect(state.totalPages).toBe(1)
      expect(state.loading).toBe(false)
      expect(state.error).toBeNull()
    })

    it('should handle pagination parameters', async () => {
      mockProjectsAPI.list.mockResolvedValue({
        items: [],
        total: 100,
        page: 2,
        page_size: 50,
        pages: 2,
      })

      await act(async () => {
        await useProjectStore.getState().fetchProjects(2, 50)
      })

      expect(mockProjectsAPI.list).toHaveBeenCalledWith(2, 50, '', undefined)
      const state = useProjectStore.getState()
      expect(state.currentPage).toBe(2)
      expect(state.pageSize).toBe(50)
    })

    it('should handle search query', async () => {
      act(() => {
        useProjectStore.setState({ searchQuery: 'test search' })
      })

      mockProjectsAPI.list.mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        page_size: 30,
        pages: 0,
      })

      await act(async () => {
        await useProjectStore.getState().fetchProjects()
      })

      expect(mockProjectsAPI.list).toHaveBeenCalledWith(
        1,
        30,
        'test search',
        undefined
      )
    })

    it('should handle archived filter', async () => {
      mockProjectsAPI.list.mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        page_size: 30,
        pages: 0,
      })

      await act(async () => {
        await useProjectStore.getState().fetchProjects(1, 30, true)
      })

      expect(mockProjectsAPI.list).toHaveBeenCalledWith(1, 30, '', true)
    })

    it('should handle undefined response gracefully', async () => {
      mockProjectsAPI.list.mockResolvedValue(undefined as any)

      await act(async () => {
        await useProjectStore.getState().fetchProjects()
      })

      const state = useProjectStore.getState()
      expect(state.projects).toEqual([])
      expect(state.totalProjects).toBe(0)
      expect(state.totalPages).toBe(1)
    })

    it('should handle response without items array', async () => {
      mockProjectsAPI.list.mockResolvedValue({
        total: 5,
        pages: 1,
      } as any)

      await act(async () => {
        await useProjectStore.getState().fetchProjects()
      })

      const state = useProjectStore.getState()
      expect(state.projects).toEqual([])
      expect(state.totalProjects).toBe(5)
    })

    it('should handle response with non-array items', async () => {
      mockProjectsAPI.list.mockResolvedValue({
        items: 'not an array' as any,
        total: 5,
        pages: 1,
      } as any)

      await act(async () => {
        await useProjectStore.getState().fetchProjects()
      })

      const state = useProjectStore.getState()
      expect(state.projects).toEqual([])
    })

    it('should handle API errors', async () => {
      mockProjectsAPI.list.mockRejectedValue(new Error('Network error'))

      await act(async () => {
        await useProjectStore.getState().fetchProjects()
      })

      const state = useProjectStore.getState()
      expect(state.error).toBe('Network error')
      expect(state.loading).toBe(false)
      expect(state.projects).toEqual([])
      expect(mockToast.error).toHaveBeenCalledWith('Network error')
    })

    it('should set loading state correctly', async () => {
      mockProjectsAPI.list.mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(
              () =>
                resolve({
                  items: [],
                  total: 0,
                  page: 1,
                  page_size: 30,
                  pages: 0,
                }),
              100
            )
          )
      )

      const fetchPromise = act(async () => {
        await useProjectStore.getState().fetchProjects()
      })

      // Check loading state is true during fetch
      expect(useProjectStore.getState().loading).toBe(true)

      await fetchPromise

      // Check loading state is false after fetch
      expect(useProjectStore.getState().loading).toBe(false)
    })
  })

  describe('fetchProject', () => {
    it('should fetch single project successfully', async () => {
      const mockProject = createMockProject({ id: '1', title: 'Test Project' })
      mockProjectsAPI.get.mockResolvedValue(mockProject)

      await act(async () => {
        await useProjectStore.getState().fetchProject('1')
      })

      const state = useProjectStore.getState()
      expect(state.currentProject).toEqual(mockProject)
      expect(state.projects).toContainEqual(mockProject)
      expect(state.taskCycle).toEqual([])
      expect(state.currentTaskIndex).toBe(0)
    })

    it('should update existing project in list', async () => {
      const existingProject = createMockProject({ id: '1', title: 'Old Title' })
      act(() => {
        useProjectStore.setState({ projects: [existingProject] })
      })

      const updatedProject = createMockProject({ id: '1', title: 'New Title' })
      mockProjectsAPI.get.mockResolvedValue(updatedProject)

      await act(async () => {
        await useProjectStore.getState().fetchProject('1')
      })

      const state = useProjectStore.getState()
      expect(state.projects).toHaveLength(1)
      expect(state.projects[0].title).toBe('New Title')
    })

    it('should add new project to list if not exists', async () => {
      const existingProject = createMockProject({ id: '1' })
      act(() => {
        useProjectStore.setState({ projects: [existingProject] })
      })

      const newProject = createMockProject({ id: '2', title: 'New Project' })
      mockProjectsAPI.get.mockResolvedValue(newProject)

      await act(async () => {
        await useProjectStore.getState().fetchProject('2')
      })

      const state = useProjectStore.getState()
      expect(state.projects).toHaveLength(2)
      expect(state.projects).toContainEqual(newProject)
    })

    it('should handle fetch errors', async () => {
      mockProjectsAPI.get.mockRejectedValue(new Error('Project not found'))

      await act(async () => {
        await useProjectStore.getState().fetchProject('999')
      })

      const state = useProjectStore.getState()
      expect(state.error).toBe('Project not found')
      expect(mockToast.error).toHaveBeenCalledWith('Project not found')
    })
  })

  describe('createProject', () => {
    it('should create project successfully', async () => {
      const projectData = {
        title: 'New Project',
        description: 'New Description',
        label_config: '<View></View>',
      }
      const createdProject = createMockProject(projectData)
      mockProjectsAPI.create.mockResolvedValue(createdProject)

      let result: Project | undefined
      await act(async () => {
        result = await useProjectStore.getState().createProject(projectData)
      })

      expect(result).toEqual(createdProject)
      const state = useProjectStore.getState()
      expect(state.projects).toContainEqual(createdProject)
      expect(state.currentProject).toEqual(createdProject)
      expect(mockToast.success).toHaveBeenCalledWith(
        'store.project.created'
      )
    })

    it('should handle creation errors', async () => {
      mockProjectsAPI.create.mockRejectedValue(new Error('Creation failed'))

      await expect(
        act(async () => {
          await useProjectStore.getState().createProject({ title: 'Test' })
        })
      ).rejects.toThrow('Creation failed')

      const state = useProjectStore.getState()
      expect(state.error).toBe('Creation failed')
      expect(mockToast.error).toHaveBeenCalledWith('Creation failed')
    })
  })

  describe('updateProject', () => {
    it('should update project successfully', async () => {
      const existingProject = createMockProject({ id: '1', title: 'Old Title' })
      act(() => {
        useProjectStore.setState({
          projects: [existingProject],
          currentProject: existingProject,
        })
      })

      const updatedProject = createMockProject({ id: '1', title: 'New Title' })
      mockProjectsAPI.update.mockResolvedValue(updatedProject)

      await act(async () => {
        await useProjectStore
          .getState()
          .updateProject('1', { title: 'New Title' })
      })

      const state = useProjectStore.getState()
      expect(state.projects[0].title).toBe('New Title')
      expect(state.currentProject?.title).toBe('New Title')
      expect(mockToast.success).toHaveBeenCalledWith(
        'store.project.updated'
      )
    })

    it('should increment label config version when label_config changes', async () => {
      const existingProject = createMockProject({ id: '1' })
      act(() => {
        useProjectStore.setState({
          projects: [existingProject],
          labelConfigVersion: 5,
        })
      })

      mockProjectsAPI.update.mockResolvedValue(existingProject)

      await act(async () => {
        await useProjectStore.getState().updateProject('1', {
          label_config: '<View>New</View>',
        })
      })

      const state = useProjectStore.getState()
      expect(state.labelConfigVersion).toBe(6)
    })

    it('should not increment version when other fields change', async () => {
      const existingProject = createMockProject({ id: '1' })
      act(() => {
        useProjectStore.setState({
          projects: [existingProject],
          labelConfigVersion: 5,
        })
      })

      mockProjectsAPI.update.mockResolvedValue(existingProject)

      await act(async () => {
        await useProjectStore
          .getState()
          .updateProject('1', { title: 'New Title' })
      })

      const state = useProjectStore.getState()
      expect(state.labelConfigVersion).toBe(5)
    })

    it('should handle update errors', async () => {
      mockProjectsAPI.update.mockRejectedValue(new Error('Update failed'))

      await act(async () => {
        await useProjectStore.getState().updateProject('1', { title: 'New' })
      })

      const state = useProjectStore.getState()
      expect(state.error).toBe('Update failed')
      expect(mockToast.error).toHaveBeenCalledWith('Update failed')
    })
  })

  describe('selectProject', () => {
    it('should select existing project', () => {
      const project1 = createMockProject({ id: '1', title: 'Project 1' })
      const project2 = createMockProject({ id: '2', title: 'Project 2' })

      act(() => {
        useProjectStore.setState({ projects: [project1, project2] })
        useProjectStore.getState().selectProject('2')
      })

      const state = useProjectStore.getState()
      expect(state.currentProject).toEqual(project2)
    })

    it('should set null for non-existent project', () => {
      act(() => {
        useProjectStore.setState({ projects: [] })
        useProjectStore.getState().selectProject('999')
      })

      const state = useProjectStore.getState()
      expect(state.currentProject).toBeNull()
    })
  })

  describe('archiveProject', () => {
    it('should archive project', async () => {
      const project = createMockProject({ id: '1', is_archived: false })
      const archivedProject = createMockProject({ id: '1', is_archived: true })

      act(() => {
        useProjectStore.setState({ projects: [project] })
      })

      mockProjectsAPI.update.mockResolvedValue(archivedProject)

      await act(async () => {
        await useProjectStore.getState().archiveProject('1')
      })

      expect(mockProjectsAPI.update).toHaveBeenCalledWith('1', {
        is_archived: true,
      })
    })

    it('should unarchive project', async () => {
      const project = createMockProject({ id: '1', is_archived: true })
      const unarchivedProject = createMockProject({
        id: '1',
        is_archived: false,
      })

      act(() => {
        useProjectStore.setState({ projects: [project] })
      })

      mockProjectsAPI.update.mockResolvedValue(unarchivedProject)

      // Access unarchiveProject directly from the store
      await act(async () => {
        await (useProjectStore.getState() as any).unarchiveProject('1')
      })

      expect(mockProjectsAPI.update).toHaveBeenCalledWith('1', {
        is_archived: false,
      })
    })
  })

  describe('deleteProject', () => {
    it('should delete project successfully', async () => {
      const project = createMockProject({ id: '1' })
      act(() => {
        useProjectStore.setState({ projects: [project] })
      })

      mockProjectsAPI.delete.mockResolvedValue(undefined)

      await act(async () => {
        await useProjectStore.getState().deleteProject('1')
      })

      const state = useProjectStore.getState()
      expect(state.projects).toHaveLength(0)
      expect(mockToast.success).toHaveBeenCalledWith(
        'store.project.deleted'
      )
    })

    it('should clear current project if deleted', async () => {
      const project = createMockProject({ id: '1' })
      act(() => {
        useProjectStore.setState({
          projects: [project],
          currentProject: project,
        })
      })

      mockProjectsAPI.delete.mockResolvedValue(undefined)

      await act(async () => {
        await useProjectStore.getState().deleteProject('1')
      })

      const state = useProjectStore.getState()
      expect(state.currentProject).toBeNull()
    })

    it('should handle deletion errors', async () => {
      mockProjectsAPI.delete.mockRejectedValue(new Error('Delete failed'))

      await act(async () => {
        await useProjectStore.getState().deleteProject('1')
      })

      const state = useProjectStore.getState()
      expect(state.error).toBe('Delete failed')
      expect(mockToast.error).toHaveBeenCalledWith('Delete failed')
    })
  })

  describe('fetchProjectTasks', () => {
    it('should fetch all tasks with pagination', async () => {
      const tasks1 = Array.from({ length: 100 }, (_, i) =>
        createMockTask({ id: `${i + 1}`, project_id: '1' })
      )
      const tasks2 = Array.from({ length: 50 }, (_, i) =>
        createMockTask({ id: `${i + 101}`, project_id: '1' })
      )

      mockProjectsAPI.getTasks
        .mockResolvedValueOnce(tasks1)
        .mockResolvedValueOnce(tasks2)

      let result: Task[] = []
      await act(async () => {
        result = await useProjectStore.getState().fetchProjectTasks('1')
      })

      expect(result).toHaveLength(150)
      expect(mockProjectsAPI.getTasks).toHaveBeenCalledTimes(2)
    })

    it('should handle empty task list', async () => {
      mockProjectsAPI.getTasks.mockResolvedValue([])

      let result: Task[] = []
      await act(async () => {
        result = await useProjectStore.getState().fetchProjectTasks('1')
      })

      expect(result).toEqual([])
    })

    it('should handle fetch errors', async () => {
      mockProjectsAPI.getTasks.mockRejectedValue(new Error('Fetch failed'))

      let result: Task[] = []
      await act(async () => {
        result = await useProjectStore.getState().fetchProjectTasks('1')
      })

      expect(result).toEqual([])
      const state = useProjectStore.getState()
      expect(state.error).toBe('Fetch failed')
      expect(mockToast.error).toHaveBeenCalledWith('Fetch failed')
    })
  })

  describe('getNextTask', () => {
    it('should load task cycle and return first task', async () => {
      const tasks = [
        createMockTask({ id: '1' }),
        createMockTask({ id: '2' }),
        createMockTask({ id: '3' }),
      ]

      mockProjectsAPI.getTasks.mockResolvedValue(tasks)

      let result: Task | null = null
      await act(async () => {
        result = await useProjectStore.getState().getNextTask('1')
      })

      const state = useProjectStore.getState()
      expect(result).toEqual(tasks[0])
      expect(state.taskCycle).toEqual(tasks)
      expect(state.currentTaskIndex).toBe(0)
      expect(state.currentTask).toEqual(tasks[0])
      expect(state.currentTaskPosition).toBe(1)
      expect(state.currentTaskTotal).toBe(3)
    })

    it('should use existing task cycle', async () => {
      const tasks = [createMockTask({ id: '1' }), createMockTask({ id: '2' })]

      act(() => {
        useProjectStore.setState({
          taskCycle: tasks,
          currentTaskIndex: 1,
        })
      })

      let result: Task | null = null
      await act(async () => {
        result = await useProjectStore.getState().getNextTask('1')
      })

      expect(result).toEqual(tasks[1])
      expect(mockProjectsAPI.getTasks).not.toHaveBeenCalled()
    })

    it('should fallback to API if no tasks in cycle', async () => {
      mockProjectsAPI.getTasks.mockResolvedValue([])
      mockProjectsAPI.getNextTask.mockResolvedValue({
        task: createMockTask({ id: '1' }),
        remaining: 5,
        current_position: 1,
        total_tasks: 5,
      })

      let result: Task | null = null
      await act(async () => {
        result = await useProjectStore.getState().getNextTask('1')
      })

      expect(result).toBeTruthy()
      expect(mockProjectsAPI.getNextTask).toHaveBeenCalled()
    })

    it('should handle no tasks available', async () => {
      mockProjectsAPI.getTasks.mockResolvedValue([])
      mockProjectsAPI.getNextTask.mockResolvedValue({
        task: null,
        remaining: 0,
      })

      let result: Task | null = null
      await act(async () => {
        result = await useProjectStore.getState().getNextTask('1')
      })

      expect(result).toBeNull()
      expect(mockToastSetup.info).toHaveBeenCalledWith('store.project.noMoreTasks')
    })

    it('should handle errors', async () => {
      mockProjectsAPI.getTasks.mockRejectedValue(new Error('Task fetch failed'))

      let result: Task | null = null
      await act(async () => {
        result = await useProjectStore.getState().getNextTask('1')
      })

      expect(result).toBeNull()
      expect(mockToast.error).toHaveBeenCalledWith('Task fetch failed')
    })
  })

  describe('setTaskByIndex', () => {
    it('should set task by valid index', () => {
      const tasks = [
        createMockTask({ id: '1' }),
        createMockTask({ id: '2' }),
        createMockTask({ id: '3' }),
      ]

      act(() => {
        useProjectStore.setState({ taskCycle: tasks, currentTaskIndex: 0 })
        useProjectStore.getState().setTaskByIndex(2)
      })

      const state = useProjectStore.getState()
      expect(state.currentTaskIndex).toBe(2)
      expect(state.currentTask).toEqual(tasks[2])
      expect(state.currentTaskPosition).toBe(3)
    })

    it('should not change state for invalid index', () => {
      const tasks = [createMockTask({ id: '1' })]

      act(() => {
        useProjectStore.setState({ taskCycle: tasks, currentTaskIndex: 0 })
        useProjectStore.getState().setTaskByIndex(5)
      })

      const state = useProjectStore.getState()
      expect(state.currentTaskIndex).toBe(0)
    })

    it('should handle negative index', () => {
      const tasks = [createMockTask({ id: '1' })]

      act(() => {
        useProjectStore.setState({ taskCycle: tasks, currentTaskIndex: 0 })
        useProjectStore.getState().setTaskByIndex(-1)
      })

      const state = useProjectStore.getState()
      expect(state.currentTaskIndex).toBe(0)
    })
  })

  describe('advanceToNextTask', () => {
    it('should advance to next task', () => {
      const tasks = [
        createMockTask({ id: '1' }),
        createMockTask({ id: '2' }),
        createMockTask({ id: '3' }),
      ]

      act(() => {
        useProjectStore.setState({
          taskCycle: tasks,
          currentTaskIndex: 0,
          currentTask: tasks[0],
        })
        useProjectStore.getState().advanceToNextTask()
      })

      const state = useProjectStore.getState()
      expect(state.currentTaskIndex).toBe(1)
      expect(state.currentTask).toEqual(tasks[1])
      expect(state.currentTaskPosition).toBe(2)
    })

    it('should wrap around to first task', () => {
      const tasks = [createMockTask({ id: '1' }), createMockTask({ id: '2' })]

      act(() => {
        useProjectStore.setState({
          taskCycle: tasks,
          currentTaskIndex: 1,
        })
        useProjectStore.getState().advanceToNextTask()
      })

      const state = useProjectStore.getState()
      expect(state.currentTaskIndex).toBe(0)
      expect(state.currentTask).toEqual(tasks[0])
      expect(mockToastSetup.info).toHaveBeenCalledWith(
        'store.project.allTasksCompletedRestart'
      )
    })

    it('should handle empty task cycle', () => {
      act(() => {
        useProjectStore.setState({ taskCycle: [], currentTaskIndex: 0 })
        useProjectStore.getState().advanceToNextTask()
      })

      const state = useProjectStore.getState()
      expect(state.currentTaskIndex).toBe(0)
    })
  })

  describe('importData', () => {
    it('should import data successfully', async () => {
      const importData = [{ text: 'Task 1' }, { text: 'Task 2' }]
      mockProjectsAPI.importData.mockResolvedValue({
        created: 2,
        total: 2,
        project_id: '1',
      })

      const project = createMockProject({ id: '1' })
      mockProjectsAPI.get.mockResolvedValue(project)

      act(() => {
        useProjectStore.setState({ currentProject: project })
      })

      await act(async () => {
        await useProjectStore.getState().importData('1', importData)
      })

      expect(mockProjectsAPI.importData).toHaveBeenCalledWith('1', {
        data: importData,
      })
      expect(mockToast.success).toHaveBeenCalledWith(
        'store.project.imported'
      )
      expect(mockProjectsAPI.get).toHaveBeenCalledWith('1')
    })

    it('should refresh projects list if not current project', async () => {
      mockProjectsAPI.importData.mockResolvedValue({
        created: 1,
        total: 1,
        project_id: '2',
      })

      mockProjectsAPI.list.mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        page_size: 30,
        pages: 0,
      })

      act(() => {
        useProjectStore.setState({
          currentProject: createMockProject({ id: '1' }),
        })
      })

      await act(async () => {
        await useProjectStore.getState().importData('2', [])
      })

      expect(mockProjectsAPI.list).toHaveBeenCalled()
    })

    it('should handle import errors', async () => {
      mockProjectsAPI.importData.mockRejectedValue(new Error('Import failed'))

      await act(async () => {
        await useProjectStore.getState().importData('1', [])
      })

      const state = useProjectStore.getState()
      expect(state.error).toBe('Import failed')
      expect(mockToast.error).toHaveBeenCalledWith('Import failed')
    })
  })

  describe('createAnnotation', () => {
    it('should create annotation and advance task', async () => {
      const annotation = createMockAnnotation()
      mockProjectsAPI.createAnnotation.mockResolvedValue(annotation)

      const tasks = [createMockTask({ id: '1' }), createMockTask({ id: '2' })]

      act(() => {
        useProjectStore.setState({
          taskCycle: tasks,
          currentTaskIndex: 0,
          currentTask: tasks[0],
        })
      })

      let result: Annotation | undefined
      await act(async () => {
        result = await useProjectStore.getState().createAnnotation('1', [])
      })

      expect(result).toEqual(annotation)
      expect(mockToast.success).toHaveBeenCalledWith('store.project.annotationSaved')

      // Task should be removed from cycle, index stays at 0 (now pointing to task 2)
      const state = useProjectStore.getState()
      expect(state.currentTaskIndex).toBe(0)
      expect(state.taskCycle).toHaveLength(1)
      expect(state.currentTask?.id).toBe('2')
    })

    it('should handle annotation errors', async () => {
      mockProjectsAPI.createAnnotation.mockRejectedValue(
        new Error('Save failed')
      )

      await expect(async () => {
        await act(async () => {
          await useProjectStore.getState().createAnnotation('1', [])
        })
      }).rejects.toThrow('Save failed')

      const state = useProjectStore.getState()
      expect(state.error).toBe('Save failed')
      expect(state.loading).toBe(false)
      expect(mockToast.error).toHaveBeenCalledWith('Save failed')
    })
  })

  describe('createAnnotationInternal', () => {
    it('should create annotation without advancing when skipAdvance is true', async () => {
      const annotation = createMockAnnotation()
      mockProjectsAPI.createAnnotation.mockResolvedValue(annotation)

      const tasks = [createMockTask({ id: '1' }), createMockTask({ id: '2' })]
      act(() => {
        useProjectStore.setState({
          taskCycle: tasks,
          currentTaskIndex: 0,
        })
      })

      await act(async () => {
        await useProjectStore.getState().createAnnotationInternal('1', {}, true)
      })

      const state = useProjectStore.getState()
      expect(state.currentTaskIndex).toBe(0) // Should not advance
    })

    it('should auto-advance when skipAdvance is false', async () => {
      const annotation = createMockAnnotation()
      mockProjectsAPI.createAnnotation.mockResolvedValue(annotation)

      const tasks = [createMockTask({ id: '1' }), createMockTask({ id: '2' })]
      act(() => {
        useProjectStore.setState({
          taskCycle: tasks,
          currentTaskIndex: 0,
        })
      })

      await act(async () => {
        await useProjectStore
          .getState()
          .createAnnotationInternal('1', {}, false)
      })

      // Task should be removed from cycle, index stays at 0 (now pointing to task 2)
      const state = useProjectStore.getState()
      expect(state.currentTaskIndex).toBe(0)
      expect(state.taskCycle).toHaveLength(1)
      expect(state.currentTask?.id).toBe('2')
    })
  })

  describe('skipTask', () => {
    it('should skip task and advance', async () => {
      const tasks = [createMockTask({ id: '1' }), createMockTask({ id: '2' })]
      const project = createMockProject({ id: '1' })

      mockProjectsAPI.getNextTask.mockResolvedValue({
        task: tasks[1],
        remaining: 1,
      })

      act(() => {
        useProjectStore.setState({
          taskCycle: tasks,
          currentTaskIndex: 0,
          currentTask: tasks[0],
          currentProject: project,
        })
      })

      await act(async () => {
        await useProjectStore.getState().skipTask()
      })

      expect(mockToastSetup.info).toHaveBeenCalledWith('store.project.taskSkipped')
    })

    it('should handle missing current task', async () => {
      act(() => {
        useProjectStore.setState({
          currentTask: null,
          currentProject: createMockProject(),
        })
      })

      await act(async () => {
        await useProjectStore.getState().skipTask()
      })

      // Should not throw error
      expect(mockToastSetup.info).not.toHaveBeenCalledWith('store.project.taskSkipped')
    })

    it('should handle missing current project', async () => {
      act(() => {
        useProjectStore.setState({
          currentTask: createMockTask({ id: '1' }),
          currentProject: null,
        })
      })

      await act(async () => {
        await useProjectStore.getState().skipTask()
      })

      // Should not throw error and not call toast
      expect(mockToastSetup.info).not.toHaveBeenCalledWith('store.project.taskSkipped')
    })

    it('should remove task from cycle when skip_queue is requeue_for_others', async () => {
      const tasks = [
        createMockTask({ id: '1' }),
        createMockTask({ id: '2' }),
        createMockTask({ id: '3' }),
      ]
      const project = createMockProject({ id: '1', skip_queue: 'requeue_for_others' })

      act(() => {
        useProjectStore.setState({
          taskCycle: tasks,
          currentTaskIndex: 0,
          currentTask: tasks[0],
          currentProject: project,
        })
      })

      await act(async () => {
        await useProjectStore.getState().skipTask()
      })

      const state = useProjectStore.getState()
      // Task '1' should be removed from cycle
      expect(state.taskCycle).toHaveLength(2)
      expect(state.taskCycle.map(t => t.id)).toEqual(['2', '3'])
      // Should now be on task '2' (index 0 in updated cycle)
      expect(state.currentTask?.id).toBe('2')
      expect(state.currentTaskIndex).toBe(0)
    })

    it('should remove task from cycle when skip_queue is ignore_skipped', async () => {
      const tasks = [
        createMockTask({ id: '1' }),
        createMockTask({ id: '2' }),
      ]
      const project = createMockProject({ id: '1', skip_queue: 'ignore_skipped' })

      act(() => {
        useProjectStore.setState({
          taskCycle: tasks,
          currentTaskIndex: 0,
          currentTask: tasks[0],
          currentProject: project,
        })
      })

      await act(async () => {
        await useProjectStore.getState().skipTask()
      })

      const state = useProjectStore.getState()
      expect(state.taskCycle).toHaveLength(1)
      expect(state.currentTask?.id).toBe('2')
    })

    it('should keep task in cycle when skip_queue is requeue_for_me', async () => {
      const tasks = [
        createMockTask({ id: '1' }),
        createMockTask({ id: '2' }),
        createMockTask({ id: '3' }),
      ]
      const project = createMockProject({ id: '1', skip_queue: 'requeue_for_me' })

      act(() => {
        useProjectStore.setState({
          taskCycle: tasks,
          currentTaskIndex: 0,
          currentTask: tasks[0],
          currentProject: project,
        })
      })

      await act(async () => {
        await useProjectStore.getState().skipTask()
      })

      const state = useProjectStore.getState()
      // Task '1' should still be in cycle
      expect(state.taskCycle).toHaveLength(3)
      // Should advance to task '2'
      expect(state.currentTask?.id).toBe('2')
      expect(state.currentTaskIndex).toBe(1)
    })

    it('should set allTasksCompleted when last task is skipped with requeue_for_others', async () => {
      const tasks = [createMockTask({ id: '1' })]
      const project = createMockProject({ id: '1', skip_queue: 'requeue_for_others' })

      act(() => {
        useProjectStore.setState({
          taskCycle: tasks,
          currentTaskIndex: 0,
          currentTask: tasks[0],
          currentProject: project,
        })
      })

      await act(async () => {
        await useProjectStore.getState().skipTask()
      })

      const state = useProjectStore.getState()
      expect(state.taskCycle).toHaveLength(0)
      expect(state.currentTask).toBeNull()
      expect(state.allTasksCompleted).toBe(true)
    })

    it('should default to requeue_for_others when skip_queue is undefined', async () => {
      const tasks = [
        createMockTask({ id: '1' }),
        createMockTask({ id: '2' }),
      ]
      // Project without skip_queue set (legacy/default)
      const project = createMockProject({ id: '1' })

      act(() => {
        useProjectStore.setState({
          taskCycle: tasks,
          currentTaskIndex: 0,
          currentTask: tasks[0],
          currentProject: project,
        })
      })

      await act(async () => {
        await useProjectStore.getState().skipTask()
      })

      const state = useProjectStore.getState()
      // Should remove task (default behavior = requeue_for_others)
      expect(state.taskCycle).toHaveLength(1)
      expect(state.currentTask?.id).toBe('2')
    })
  })


  describe('evaluateLLMResponses', () => {
    it('should show not implemented message', async () => {
      await act(async () => {
        await useProjectStore.getState().evaluateLLMResponses('1')
      })

      expect(mockToastSetup.info).toHaveBeenCalledWith(
        'store.project.evaluationNotImplemented'
      )
    })
  })

  describe('UI Actions', () => {
    describe('setSearchQuery', () => {
      it('should update search query and reset page', () => {
        act(() => {
          useProjectStore.setState({ currentPage: 5 })
          useProjectStore.getState().setSearchQuery('test search')
        })

        const state = useProjectStore.getState()
        expect(state.searchQuery).toBe('test search')
        expect(state.currentPage).toBe(1)
      })
    })

    describe('setCurrentPage', () => {
      it('should update page and fetch projects', async () => {
        mockProjectsAPI.list.mockResolvedValue({
          items: [],
          total: 0,
          page: 2,
          page_size: 30,
          pages: 1,
        })

        await act(async () => {
          await useProjectStore.getState().setCurrentPage(2)
        })

        const state = useProjectStore.getState()
        expect(state.currentPage).toBe(2)
        expect(mockProjectsAPI.list).toHaveBeenCalledWith(2, 30, '', undefined)
      })
    })

    describe('setPageSize', () => {
      it('should update page size and reset to page 1', async () => {
        mockProjectsAPI.list.mockResolvedValue({
          items: [],
          total: 0,
          page: 1,
          page_size: 50,
          pages: 1,
        })

        act(() => {
          useProjectStore.setState({ currentPage: 5 })
        })

        await act(async () => {
          await useProjectStore.getState().setPageSize(50)
        })

        const state = useProjectStore.getState()
        expect(state.pageSize).toBe(50)
        expect(state.currentPage).toBe(1)
        expect(mockProjectsAPI.list).toHaveBeenCalledWith(1, 50, '', undefined)
      })
    })

    describe('clearError', () => {
      it('should clear error state', () => {
        act(() => {
          useProjectStore.setState({ error: 'Some error' })
          useProjectStore.getState().clearError()
        })

        const state = useProjectStore.getState()
        expect(state.error).toBeNull()
      })
    })
  })

  describe('State Reset and Cleanup', () => {
    it('should clear task cycle when fetching new project', async () => {
      const tasks = [createMockTask({ id: '1' })]
      act(() => {
        useProjectStore.setState({
          taskCycle: tasks,
          currentTaskIndex: 5,
        })
      })

      mockProjectsAPI.get.mockResolvedValue(createMockProject({ id: '2' }))

      await act(async () => {
        await useProjectStore.getState().fetchProject('2')
      })

      const state = useProjectStore.getState()
      expect(state.taskCycle).toEqual([])
      expect(state.currentTaskIndex).toBe(0)
    })
  })

  describe('Edge Cases', () => {
    it('should handle concurrent fetchProjects calls', async () => {
      mockProjectsAPI.list.mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(
              () =>
                resolve({
                  items: [createMockProject()],
                  total: 1,
                  page: 1,
                  page_size: 30,
                  pages: 1,
                }),
              50
            )
          )
      )

      await act(async () => {
        await Promise.all([
          useProjectStore.getState().fetchProjects(),
          useProjectStore.getState().fetchProjects(),
        ])
      })

      // Should handle gracefully without crashing
      const state = useProjectStore.getState()
      expect(state.projects).toBeDefined()
    })

    it('should handle rapid task advancement', () => {
      const tasks = [
        createMockTask({ id: '1' }),
        createMockTask({ id: '2' }),
        createMockTask({ id: '3' }),
      ]

      act(() => {
        useProjectStore.setState({ taskCycle: tasks, currentTaskIndex: 0 })
        useProjectStore.getState().advanceToNextTask()
        useProjectStore.getState().advanceToNextTask()
        useProjectStore.getState().advanceToNextTask()
      })

      const state = useProjectStore.getState()
      expect(state.currentTaskIndex).toBe(0) // Wrapped around
    })

    it('should handle non-Error thrown objects', async () => {
      mockProjectsAPI.list.mockRejectedValue('String error')

      await act(async () => {
        await useProjectStore.getState().fetchProjects()
      })

      const state = useProjectStore.getState()
      expect(state.error).toBe('store.project.fetchFailed')
    })

    it('should handle null currentProject on delete', async () => {
      mockProjectsAPI.delete.mockResolvedValue(undefined)

      act(() => {
        useProjectStore.setState({ currentProject: null })
      })

      await act(async () => {
        await useProjectStore.getState().deleteProject('1')
      })

      // Should not crash
      const state = useProjectStore.getState()
      expect(state.currentProject).toBeNull()
    })
  })

  describe('Concurrent Operations', () => {
    it('should handle concurrent project updates', async () => {
      const project = createMockProject({ id: '1' })
      act(() => {
        useProjectStore.setState({ projects: [project] })
      })

      mockProjectsAPI.update.mockResolvedValue(project)

      await act(async () => {
        await Promise.all([
          useProjectStore.getState().updateProject('1', { title: 'Title 1' }),
          useProjectStore
            .getState()
            .updateProject('1', { description: 'Desc 1' }),
        ])
      })

      // Should complete without errors
      expect(mockProjectsAPI.update).toHaveBeenCalledTimes(2)
    })

    it('should handle concurrent task fetching', async () => {
      mockProjectsAPI.getTasks.mockResolvedValue([createMockTask()])

      await act(async () => {
        await Promise.all([
          useProjectStore.getState().fetchProjectTasks('1'),
          useProjectStore.getState().fetchProjectTasks('1'),
        ])
      })

      // Should not crash
      expect(mockProjectsAPI.getTasks).toHaveBeenCalled()
    })

    it('should handle state updates during async operations', async () => {
      mockProjectsAPI.list.mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(
              () =>
                resolve({
                  items: [createMockProject()],
                  total: 1,
                  page: 1,
                  page_size: 30,
                  pages: 1,
                }),
              100
            )
          )
      )

      const fetchPromise = act(async () => {
        await useProjectStore.getState().fetchProjects()
      })

      // Update state during fetch
      act(() => {
        useProjectStore.getState().setSearchQuery('test')
      })

      await fetchPromise

      // Should complete successfully
      const state = useProjectStore.getState()
      expect(state.searchQuery).toBe('test')
    })
  })

  describe('completeCurrentTask', () => {
    it('should fetch next task in auto mode', async () => {
      const mockNextTask = createMockTask({ id: '2' })
      mockProjectsAPI.getNextTask.mockResolvedValue(mockNextTask)

      act(() => {
        useProjectStore.setState({
          currentProject: createMockProject({
            id: '1',
            assignment_mode: 'auto',
          }),
          currentTask: createMockTask({ id: '1' }),
          taskCycle: [createMockTask({ id: '1' })],
          currentTaskIndex: 0,
        })
      })

      await act(async () => {
        await useProjectStore.getState().completeCurrentTask()
      })

      expect(mockProjectsAPI.getNextTask).toHaveBeenCalledWith('1')
    })

    it('should set allTasksCompleted when no next task in auto mode', async () => {
      mockProjectsAPI.getNextTask.mockResolvedValue(null)

      act(() => {
        useProjectStore.setState({
          currentProject: createMockProject({
            id: '1',
            assignment_mode: 'auto',
          }),
          currentTask: createMockTask({ id: '1' }),
          taskCycle: [createMockTask({ id: '1' })],
          currentTaskIndex: 0,
        })
      })

      await act(async () => {
        await useProjectStore.getState().completeCurrentTask()
      })

      expect(useProjectStore.getState().allTasksCompleted).toBe(true)
    })

    it('should remove task from cycle in open mode', async () => {
      const tasks = [
        createMockTask({ id: '1' }),
        createMockTask({ id: '2' }),
        createMockTask({ id: '3' }),
      ]

      act(() => {
        useProjectStore.setState({
          currentProject: createMockProject({ assignment_mode: undefined }),
          currentTask: tasks[0],
          taskCycle: tasks,
          currentTaskIndex: 0,
        })
      })

      await act(async () => {
        await useProjectStore.getState().completeCurrentTask()
      })

      const state = useProjectStore.getState()
      expect(state.taskCycle).toHaveLength(2)
      expect(state.currentTask?.id).toBe('2')
    })

    it('should set allTasksCompleted when last task completed in open mode', async () => {
      act(() => {
        useProjectStore.setState({
          currentProject: createMockProject({ assignment_mode: undefined }),
          currentTask: createMockTask({ id: '1' }),
          taskCycle: [createMockTask({ id: '1' })],
          currentTaskIndex: 0,
        })
      })

      await act(async () => {
        await useProjectStore.getState().completeCurrentTask()
      })

      const state = useProjectStore.getState()
      expect(state.allTasksCompleted).toBe(true)
      expect(state.taskCycle).toHaveLength(0)
      expect(state.currentTask).toBeNull()
    })
  })

  describe('importData', () => {
    it('should import data and refresh current project', async () => {
      const mockResult = { created: 5, errors: [] }
      mockProjectsAPI.importData.mockResolvedValue(mockResult)
      // fetchProject internally calls projectsAPI.get
      mockProjectsAPI.get.mockResolvedValue(createMockProject({ id: 'p1' }))

      act(() => {
        useProjectStore.setState({
          currentProject: createMockProject({ id: 'p1' }),
        })
      })

      await act(async () => {
        await useProjectStore.getState().importData('p1', [{ text: 'test' }])
      })

      expect(mockProjectsAPI.importData).toHaveBeenCalledWith('p1', {
        data: [{ text: 'test' }],
      })
    })

    it('should refresh project list when importing to non-current project', async () => {
      const mockResult = { created: 3, errors: [] }
      mockProjectsAPI.importData.mockResolvedValue(mockResult)
      mockProjectsAPI.list.mockResolvedValue({
        items: [],
        total: 0,
        pages: 0,
      })

      act(() => {
        useProjectStore.setState({
          currentProject: createMockProject({ id: 'other' }),
        })
      })

      await act(async () => {
        await useProjectStore.getState().importData('p1', [{ text: 'test' }])
      })

      expect(mockProjectsAPI.list).toHaveBeenCalled()
    })

    it('should handle import error', async () => {
      mockProjectsAPI.importData.mockRejectedValue(
        new Error('Import failed')
      )

      await act(async () => {
        await useProjectStore.getState().importData('p1', [{ text: 'test' }])
      })

      const state = useProjectStore.getState()
      expect(state.error).toBe('Import failed')
      expect(state.loading).toBe(false)
    })
  })

  describe('createAnnotation with max annotations error', () => {
    it('should handle max annotations limit in open mode', async () => {
      mockProjectsAPI.createAnnotation.mockRejectedValue(
        new Error('Maximum annotations limit reached')
      )

      const tasks = [
        createMockTask({ id: '1' }),
        createMockTask({ id: '2' }),
      ]

      act(() => {
        useProjectStore.setState({
          currentProject: createMockProject({ assignment_mode: undefined }),
          currentTask: tasks[0],
          taskCycle: tasks,
          currentTaskIndex: 0,
        })
      })

      await act(async () => {
        const result = await useProjectStore
          .getState()
          .createAnnotation('1', [])
        expect(result).toBeNull()
      })

      const state = useProjectStore.getState()
      expect(state.taskCycle).toHaveLength(1)
      expect(state.loading).toBe(false)
    })

    it('should set allTasksCompleted when max annotations on last task in open mode', async () => {
      mockProjectsAPI.createAnnotation.mockRejectedValue(
        new Error('Maximum annotations limit reached')
      )

      act(() => {
        useProjectStore.setState({
          currentProject: createMockProject({ assignment_mode: undefined }),
          currentTask: createMockTask({ id: '1' }),
          taskCycle: [createMockTask({ id: '1' })],
          currentTaskIndex: 0,
        })
      })

      await act(async () => {
        await useProjectStore.getState().createAnnotation('1', [])
      })

      expect(useProjectStore.getState().allTasksCompleted).toBe(true)
    })

    it('should handle max annotations limit in auto mode', async () => {
      mockProjectsAPI.createAnnotation.mockRejectedValue(
        new Error('Maximum annotations limit reached')
      )
      mockProjectsAPI.getNextTask.mockResolvedValue(null)

      act(() => {
        useProjectStore.setState({
          currentProject: createMockProject({
            id: 'p1',
            assignment_mode: 'auto',
          }),
          currentTask: createMockTask({ id: '1' }),
          taskCycle: [createMockTask({ id: '1' })],
          currentTaskIndex: 0,
        })
      })

      await act(async () => {
        await useProjectStore.getState().createAnnotation('1', [])
      })

      expect(useProjectStore.getState().allTasksCompleted).toBe(true)
    })
  })

  describe('skipTask', () => {
    it('should skip task with requeue_for_me (keeps task in cycle)', async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}),
      }) as any

      const tasks = [
        createMockTask({ id: '1' }),
        createMockTask({ id: '2' }),
      ]

      act(() => {
        useProjectStore.setState({
          currentProject: createMockProject({
            id: 'p1',
            skip_queue: 'requeue_for_me',
          }),
          currentTask: tasks[0],
          taskCycle: tasks,
          currentTaskIndex: 0,
        })
      })

      await act(async () => {
        await useProjectStore.getState().skipTask('Test comment')
      })

      // Task should still be in cycle (requeue_for_me)
      expect(useProjectStore.getState().taskCycle).toHaveLength(2)
    })

    it('should skip task with requeue_for_others (removes from cycle)', async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}),
      }) as any

      const tasks = [
        createMockTask({ id: '1' }),
        createMockTask({ id: '2' }),
      ]

      act(() => {
        useProjectStore.setState({
          currentProject: createMockProject({
            id: 'p1',
            skip_queue: 'requeue_for_others',
          }),
          currentTask: tasks[0],
          taskCycle: tasks,
          currentTaskIndex: 0,
        })
      })

      await act(async () => {
        await useProjectStore.getState().skipTask()
      })

      expect(useProjectStore.getState().taskCycle).toHaveLength(1)
    })

    it('should handle skip error', async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: false,
        json: () => Promise.resolve({ detail: 'Skip failed' }),
      }) as any

      act(() => {
        useProjectStore.setState({
          currentProject: createMockProject({ id: 'p1' }),
          currentTask: createMockTask({ id: '1' }),
          taskCycle: [createMockTask({ id: '1' })],
          currentTaskIndex: 0,
        })
      })

      await expect(
        act(async () => {
          await useProjectStore.getState().skipTask()
        })
      ).rejects.toThrow('Skip failed')
    })

    it('should do nothing when no current task or project', async () => {
      act(() => {
        useProjectStore.setState({
          currentProject: null,
          currentTask: null,
        })
      })

      await act(async () => {
        await useProjectStore.getState().skipTask()
      })

      // Should not throw, just return early
    })

    it('should set allTasksCompleted when skipping last task', async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}),
      }) as any

      act(() => {
        useProjectStore.setState({
          currentProject: createMockProject({
            id: 'p1',
            skip_queue: 'requeue_for_others',
          }),
          currentTask: createMockTask({ id: '1' }),
          taskCycle: [createMockTask({ id: '1' })],
          currentTaskIndex: 0,
        })
      })

      await act(async () => {
        await useProjectStore.getState().skipTask()
      })

      expect(useProjectStore.getState().allTasksCompleted).toBe(true)
    })

    it('should skip task in auto mode and fetch next', async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}),
      }) as any

      const mockNextTask = createMockTask({ id: '2' })
      mockProjectsAPI.getNextTask.mockResolvedValue(mockNextTask)

      act(() => {
        useProjectStore.setState({
          currentProject: createMockProject({
            id: 'p1',
            assignment_mode: 'auto',
          }),
          currentTask: createMockTask({ id: '1' }),
          taskCycle: [createMockTask({ id: '1' })],
          currentTaskIndex: 0,
        })
      })

      await act(async () => {
        await useProjectStore.getState().skipTask()
      })

      expect(mockProjectsAPI.getNextTask).toHaveBeenCalledWith('p1')
    })
  })

  describe('resetAnnotationCompletion', () => {
    it('should reset allTasksCompleted flag', () => {
      act(() => {
        useProjectStore.setState({ allTasksCompleted: true })
      })

      act(() => {
        useProjectStore.getState().resetAnnotationCompletion()
      })

      expect(useProjectStore.getState().allTasksCompleted).toBe(false)
    })
  })

  describe('Selectors and Computed Values', () => {
    it('should derive task position correctly', () => {
      const tasks = [
        createMockTask({ id: '1' }),
        createMockTask({ id: '2' }),
        createMockTask({ id: '3' }),
      ]

      act(() => {
        useProjectStore.setState({
          taskCycle: tasks,
          currentTaskIndex: 1,
        })
        useProjectStore.getState().setTaskByIndex(1)
      })

      const state = useProjectStore.getState()
      expect(state.currentTaskPosition).toBe(2)
      expect(state.currentTaskTotal).toBe(3)
    })

    it('should calculate pagination correctly', () => {
      act(() => {
        useProjectStore.setState({
          totalProjects: 150,
          pageSize: 30,
          totalPages: 5,
        })
      })

      const state = useProjectStore.getState()
      expect(state.totalPages).toBe(5)
      expect(state.pageSize).toBe(30)
    })
  })
})
