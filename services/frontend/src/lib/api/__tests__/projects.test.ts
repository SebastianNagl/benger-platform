/**
 * Tests for the projectsAPI
 */

import apiClient from '@/lib/api'
import {
  Annotation,
  ImportResult,
  PaginatedResponse,
  Project,
  Task,
} from '@/types/labelStudio'
import { projectsAPI } from '../projects'

// Mock the apiClient
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
    patch: jest.fn(),
    delete: jest.fn(),
    put: jest.fn(),
  },
}))

describe('projectsAPI', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('list', () => {
    it('should list projects with default parameters', async () => {
      const mockResponse: PaginatedResponse<Project> = {
        items: [
          {
            id: 'proj-1',
            title: 'Project 1',
            description: 'Description 1',
            created_at: '2024-01-01T00:00:00Z',
          } as Project,
        ],
        total: 1,
        page: 1,
        page_size: 100,
        total_pages: 1,
      }

      ;(apiClient.get as jest.Mock).mockResolvedValue(mockResponse)

      const result = await projectsAPI.list()

      expect(apiClient.get).toHaveBeenCalledWith(
        expect.stringMatching(/^\/projects\/\?page=1&page_size=100&_=\d+$/)
      )
      expect(result).toEqual(mockResponse)
    })

    it('should list projects with pagination', async () => {
      const mockResponse: PaginatedResponse<Project> = {
        items: [],
        total: 50,
        page: 2,
        page_size: 20,
        total_pages: 3,
      }

      ;(apiClient.get as jest.Mock).mockResolvedValue(mockResponse)

      await projectsAPI.list(2, 20)

      expect(apiClient.get).toHaveBeenCalledWith(
        expect.stringMatching(/page=2&page_size=20/)
      )
    })

    it('should list projects with search filter', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue({ items: [], total: 0 })

      await projectsAPI.list(1, 100, 'test search')

      expect(apiClient.get).toHaveBeenCalledWith(
        expect.stringMatching(/search=test\+search/)
      )
    })

    it('should list archived projects only', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue({ items: [], total: 0 })

      await projectsAPI.list(1, 100, undefined, true)

      expect(apiClient.get).toHaveBeenCalledWith(
        expect.stringMatching(/is_archived=true/)
      )
    })

    it('should list active projects only', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue({ items: [], total: 0 })

      await projectsAPI.list(1, 100, undefined, false)

      expect(apiClient.get).toHaveBeenCalledWith(
        expect.stringMatching(/is_archived=false/)
      )
    })

    it('should not include is_archived param when undefined', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue({ items: [], total: 0 })

      await projectsAPI.list(1, 100, undefined, undefined)

      const callArg = (apiClient.get as jest.Mock).mock.calls[0][0]
      expect(callArg).not.toMatch(/is_archived/)
    })

    it('should include cache-busting parameter', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue({ items: [], total: 0 })

      await projectsAPI.list()

      expect(apiClient.get).toHaveBeenCalledWith(expect.stringMatching(/_=\d+/))
    })
  })

  describe('get', () => {
    it('should get a specific project', async () => {
      const mockProject: Project = {
        id: 'proj-1',
        title: 'Project 1',
        description: 'Description',
        created_at: '2024-01-01T00:00:00Z',
      } as Project

      ;(apiClient.get as jest.Mock).mockResolvedValue(mockProject)

      const result = await projectsAPI.get('proj-1')

      expect(apiClient.get).toHaveBeenCalledWith(
        expect.stringMatching(/^\/projects\/proj-1\?_=\d+$/)
      )
      expect(result).toEqual(mockProject)
    })

    it('should include cache-busting parameter', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue({} as Project)

      await projectsAPI.get('proj-1')

      expect(apiClient.get).toHaveBeenCalledWith(
        expect.stringMatching(/\?_=\d+$/)
      )
    })
  })

  describe('create', () => {
    it('should create a new project', async () => {
      const projectData = {
        title: 'New Project',
        description: 'New Description',
      }

      const mockResponse: Project = {
        id: 'proj-new',
        title: 'New Project',
        description: 'New Description',
        created_at: '2024-01-01T00:00:00Z',
      } as Project

      ;(apiClient.post as jest.Mock).mockResolvedValue(mockResponse)

      const result = await projectsAPI.create(projectData)

      expect(apiClient.post).toHaveBeenCalledWith('/projects/', projectData)
      expect(result).toEqual(mockResponse)
    })
  })

  describe('update', () => {
    it('should update a project', async () => {
      const updateData = {
        title: 'Updated Title',
        description: 'Updated Description',
      }

      const mockResponse: Project = {
        id: 'proj-1',
        title: 'Updated Title',
        description: 'Updated Description',
        created_at: '2024-01-01T00:00:00Z',
      } as Project

      ;(apiClient.patch as jest.Mock).mockResolvedValue(mockResponse)

      const result = await projectsAPI.update('proj-1', updateData)

      expect(apiClient.patch).toHaveBeenCalledWith(
        '/projects/proj-1',
        updateData
      )
      expect(result).toEqual(mockResponse)
    })
  })

  describe('delete', () => {
    it('should delete a project', async () => {
      ;(apiClient.delete as jest.Mock).mockResolvedValue(undefined)

      await projectsAPI.delete('proj-1')

      expect(apiClient.delete).toHaveBeenCalledWith('/projects/proj-1')
    })
  })

  describe('importData', () => {
    it('should import data into a project', async () => {
      const importData = {
        data: [{ text: 'Sample text' }],
        meta: { source: 'test' },
      }

      const mockResponse: ImportResult = {
        task_count: 1,
        annotation_count: 0,
        prediction_count: 0,
        duration: 0.5,
        file_upload_ids: [],
        could_be_tasks_list: false,
        found_formats: [],
        data_columns: [],
      }

      ;(apiClient.post as jest.Mock).mockResolvedValue(mockResponse)

      const result = await projectsAPI.importData('proj-1', importData)

      expect(apiClient.post).toHaveBeenCalledWith(
        '/projects/proj-1/import',
        importData
      )
      expect(result).toEqual(mockResponse)
    })
  })

  describe('getTasks', () => {
    it('should get tasks with default parameters', async () => {
      const mockResponse = {
        items: [
          { id: 'task-1', data: { text: 'Task 1' } } as Task,
          { id: 'task-2', data: { text: 'Task 2' } } as Task,
        ],
      }

      ;(apiClient.get as jest.Mock).mockResolvedValue(mockResponse)

      const result = await projectsAPI.getTasks('proj-1')

      expect(apiClient.get).toHaveBeenCalledWith(
        expect.stringMatching(
          /^\/projects\/proj-1\/tasks\?page=1&page_size=30$/
        )
      )
      expect(result).toEqual(mockResponse.items)
    })

    it('should get tasks with pagination', async () => {
      const mockResponse = { items: [] }
      ;(apiClient.get as jest.Mock).mockResolvedValue(mockResponse)

      await projectsAPI.getTasks('proj-1', { page: 2, pageSize: 50 })

      expect(apiClient.get).toHaveBeenCalledWith(
        expect.stringMatching(/page=2&page_size=50/)
      )
    })

    it('should filter only labeled tasks', async () => {
      const mockResponse = { items: [] }
      ;(apiClient.get as jest.Mock).mockResolvedValue(mockResponse)

      await projectsAPI.getTasks('proj-1', { onlyLabeled: true })

      expect(apiClient.get).toHaveBeenCalledWith(
        expect.stringMatching(/only_labeled=true/)
      )
    })

    it('should filter only unlabeled tasks', async () => {
      const mockResponse = { items: [] }
      ;(apiClient.get as jest.Mock).mockResolvedValue(mockResponse)

      await projectsAPI.getTasks('proj-1', { onlyUnlabeled: true })

      expect(apiClient.get).toHaveBeenCalledWith(
        expect.stringMatching(/only_unlabeled=true/)
      )
    })

    it('should pass excludeMyAnnotations to the API', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue({ items: [] })
      await projectsAPI.getTasks('proj-1', { excludeMyAnnotations: true })
      expect(apiClient.get).toHaveBeenCalledWith(
        expect.stringMatching(/exclude_my_annotations=true/)
      )
    })

    it('should pass search / date / sort options when set', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue({ items: [] })
      await projectsAPI.getTasks('proj-1', {
        search: 'hello',
        dateFrom: '2025-01-01',
        dateTo: '2025-12-31',
        sortBy: 'created',
        sortOrder: 'desc',
      })
      const url = (apiClient.get as jest.Mock).mock.calls[0][0] as string
      expect(url).toMatch(/search=hello/)
      expect(url).toMatch(/date_from=2025-01-01/)
      expect(url).toMatch(/date_to=2025-12-31/)
      expect(url).toMatch(/sort_by=created/)
      expect(url).toMatch(/sort_order=desc/)
    })

    it('should handle array response format', async () => {
      const mockResponse = [{ id: 'task-1', data: { text: 'Task 1' } } as Task]

      ;(apiClient.get as jest.Mock).mockResolvedValue(mockResponse)

      const result = await projectsAPI.getTasks('proj-1')

      expect(result).toEqual(mockResponse)
    })

    it('should handle empty response', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue(null)

      const result = await projectsAPI.getTasks('proj-1')

      expect(result).toEqual([])
    })
  })

  describe('getTasksPage', () => {
    it('should return the full pagination envelope on default options', async () => {
      const mockResponse = {
        items: [{ id: 't1' } as Task],
        total: 1,
        page: 1,
        page_size: 50,
        pages: 1,
      }
      ;(apiClient.get as jest.Mock).mockResolvedValue(mockResponse)

      const result = await projectsAPI.getTasksPage('proj-1')

      expect(apiClient.get).toHaveBeenCalledWith(
        expect.stringMatching(
          /^\/projects\/proj-1\/tasks\?page=1&page_size=50$/
        )
      )
      expect(result).toEqual(mockResponse)
    })

    it('should forward all filter options to the API', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue({
        items: [], total: 0, page: 2, page_size: 25, pages: 0,
      })
      await projectsAPI.getTasksPage('proj-1', {
        page: 2,
        pageSize: 25,
        onlyLabeled: true,
        onlyUnlabeled: false,
        excludeMyAnnotations: true,
        search: 'hello',
        dateFrom: '2025-01-01',
        dateTo: '2025-12-31',
        sortBy: 'annotations',
        sortOrder: 'asc',
      })
      const url = (apiClient.get as jest.Mock).mock.calls[0][0] as string
      expect(url).toMatch(/page=2&page_size=25/)
      expect(url).toMatch(/only_labeled=true/)
      expect(url).toMatch(/only_unlabeled=false/)
      expect(url).toMatch(/exclude_my_annotations=true/)
      expect(url).toMatch(/search=hello/)
      expect(url).toMatch(/date_from=2025-01-01/)
      expect(url).toMatch(/date_to=2025-12-31/)
      expect(url).toMatch(/sort_by=annotations/)
      expect(url).toMatch(/sort_order=asc/)
    })

    it('should fall back to defaults when the response shape is an array', async () => {
      const mockResponse = [{ id: 't1' } as Task]
      ;(apiClient.get as jest.Mock).mockResolvedValue(mockResponse)
      const result = await projectsAPI.getTasksPage('proj-1', { pageSize: 100 })
      expect(result).toEqual({
        items: mockResponse,
        total: 1,
        page: 1,
        page_size: 100,
        pages: 1,
      })
    })

    it('should return zeros on a null response', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue(null)
      const result = await projectsAPI.getTasksPage('proj-1', { pageSize: 75 })
      expect(result).toEqual({
        items: [],
        total: 0,
        page: 1,
        page_size: 75,
        pages: 0,
      })
    })

    it('should fill missing envelope fields with caller defaults', async () => {
      // Backend that returns just { items: [...] } without total/page/pages.
      ;(apiClient.get as jest.Mock).mockResolvedValue({ items: [{ id: 't1' } as Task] })
      const result = await projectsAPI.getTasksPage('proj-1', { page: 3 })
      expect(result.items).toHaveLength(1)
      expect(result.page).toBe(3)
      expect(result.pages).toBe(0)
    })
  })

  describe('getTaskIds', () => {
    it('should hit /tasks?ids_only=true and return the ID envelope', async () => {
      const mockResponse = { ids: ['t1', 't2'], total: 2, truncated: false }
      ;(apiClient.get as jest.Mock).mockResolvedValue(mockResponse)
      const result = await projectsAPI.getTaskIds('proj-1')
      const url = (apiClient.get as jest.Mock).mock.calls[0][0] as string
      expect(url).toMatch(/ids_only=true/)
      expect(result).toEqual(mockResponse)
    })

    it('should forward every filter option', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue({
        ids: [], total: 0, truncated: false,
      })
      await projectsAPI.getTaskIds('proj-1', {
        onlyLabeled: true,
        onlyUnlabeled: false,
        excludeMyAnnotations: true,
        search: 'foo',
        dateFrom: '2025-01-01',
        dateTo: '2025-12-31',
        idsLimit: 1000,
      })
      const url = (apiClient.get as jest.Mock).mock.calls[0][0] as string
      expect(url).toMatch(/only_labeled=true/)
      expect(url).toMatch(/only_unlabeled=false/)
      expect(url).toMatch(/exclude_my_annotations=true/)
      expect(url).toMatch(/search=foo/)
      expect(url).toMatch(/date_from=2025-01-01/)
      expect(url).toMatch(/date_to=2025-12-31/)
      expect(url).toMatch(/ids_limit=1000/)
    })

    it('should default to empty + total=0 when API returns falsy', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue(null)
      const result = await projectsAPI.getTaskIds('proj-1')
      expect(result).toEqual({ ids: [], total: 0, truncated: false })
    })

    it('should preserve truncated=true on a capped response', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue({
        ids: ['t1'], total: 50000, truncated: true,
      })
      const result = await projectsAPI.getTaskIds('proj-1')
      expect(result.truncated).toBe(true)
      expect(result.total).toBe(50000)
    })
  })

  describe('getNextTask', () => {
    it('should get next task to annotate', async () => {
      const mockResponse = {
        task: { id: 'task-1', data: { text: 'Next task' } } as Task,
        remaining: 5,
        current_position: 1,
        total_tasks: 10,
      }

      ;(apiClient.get as jest.Mock).mockResolvedValue(mockResponse)

      const result = await projectsAPI.getNextTask('proj-1')

      expect(apiClient.get).toHaveBeenCalledWith('/projects/proj-1/next')
      expect(result).toEqual(mockResponse)
    })

    it('should handle no tasks remaining', async () => {
      const mockResponse = {
        task: null,
        remaining: 0,
      }

      ;(apiClient.get as jest.Mock).mockResolvedValue(mockResponse)

      const result = await projectsAPI.getNextTask('proj-1')

      expect(result.task).toBeNull()
      expect(result.remaining).toBe(0)
    })
  })

  describe('getTask', () => {
    it('should get a specific task', async () => {
      const mockTask: Task = {
        id: 'task-1',
        data: { text: 'Task data' },
        project: 'proj-1',
      } as Task

      ;(apiClient.get as jest.Mock).mockResolvedValue(mockTask)

      const result = await projectsAPI.getTask('task-1')

      expect(apiClient.get).toHaveBeenCalledWith('/projects/tasks/task-1')
      expect(result).toEqual(mockTask)
    })
  })

  describe('createAnnotation', () => {
    it('should create an annotation', async () => {
      const annotationData = {
        result: [{ value: { text: 'annotation' } }],
      }

      const mockAnnotation: Annotation = {
        id: 'ann-1',
        task: 'task-1',
        result: annotationData.result,
        created_at: '2024-01-01T00:00:00Z',
      } as Annotation

      ;(apiClient.post as jest.Mock).mockResolvedValue(mockAnnotation)

      const result = await projectsAPI.createAnnotation(
        'task-1',
        annotationData
      )

      expect(apiClient.post).toHaveBeenCalledWith(
        '/projects/tasks/task-1/annotations',
        annotationData
      )
      expect(result).toEqual(mockAnnotation)
    })
  })

  describe('getTaskAnnotations', () => {
    it('should get annotations for a task', async () => {
      const mockAnnotations: Annotation[] = [
        { id: 'ann-1', task: 'task-1' } as Annotation,
        { id: 'ann-2', task: 'task-1' } as Annotation,
      ]

      ;(apiClient.get as jest.Mock).mockResolvedValue(mockAnnotations)

      const result = await projectsAPI.getTaskAnnotations('task-1')

      expect(apiClient.get).toHaveBeenCalledWith(
        '/projects/tasks/task-1/annotations'
      )
      expect(result).toEqual(mockAnnotations)
    })
  })

  describe('updateAnnotation', () => {
    it('should update an annotation', async () => {
      const updateData = {
        result: [{ value: { text: 'updated annotation' } }],
      }

      const mockAnnotation: Annotation = {
        id: 'ann-1',
        task: 'task-1',
        result: updateData.result,
      } as Annotation

      ;(apiClient.patch as jest.Mock).mockResolvedValue(mockAnnotation)

      const result = await projectsAPI.updateAnnotation('ann-1', updateData)

      expect(apiClient.patch).toHaveBeenCalledWith(
        '/projects/annotations/ann-1',
        updateData
      )
      expect(result).toEqual(mockAnnotation)
    })
  })

  describe('export', () => {
    it('should export project in JSON format', async () => {
      const mockBlob = new Blob(['test data'], { type: 'application/json' })
      ;(apiClient.get as jest.Mock).mockResolvedValue(mockBlob)

      const result = await projectsAPI.export('proj-1', 'json', true)

      expect(apiClient.get).toHaveBeenCalledWith(
        '/projects/proj-1/export?format=json&download=true'
      )
      expect(result).toEqual(mockBlob)
    })

    it('should export project in CSV format', async () => {
      const mockBlob = new Blob(['test data'], { type: 'text/csv' })
      ;(apiClient.get as jest.Mock).mockResolvedValue(mockBlob)

      await projectsAPI.export('proj-1', 'csv', false)

      expect(apiClient.get).toHaveBeenCalledWith(
        '/projects/proj-1/export?format=csv&download=false'
      )
    })
  })

  describe('bulk operations on tasks', () => {
    it('should bulk delete tasks', async () => {
      const mockResponse = { deleted: 3 }
      ;(apiClient.post as jest.Mock).mockResolvedValue(mockResponse)

      const result = await projectsAPI.bulkDeleteTasks('proj-1', [
        'task-1',
        'task-2',
        'task-3',
      ])

      expect(apiClient.post).toHaveBeenCalledWith(
        '/projects/proj-1/tasks/bulk-delete',
        {
          task_ids: ['task-1', 'task-2', 'task-3'],
        }
      )
      expect(result).toEqual(mockResponse)
    })

    it('should bulk export tasks', async () => {
      const mockBlob = new Blob(['test data'], { type: 'application/json' })
      ;(apiClient.post as jest.Mock).mockResolvedValue(mockBlob)

      const result = await projectsAPI.bulkExportTasks(
        'proj-1',
        ['task-1', 'task-2'],
        'json'
      )

      expect(apiClient.post).toHaveBeenCalledWith(
        '/projects/proj-1/tasks/bulk-export',
        {
          task_ids: ['task-1', 'task-2'],
          format: 'json',
        }
      )
      expect(result).toEqual(mockBlob)
    })

    it('should bulk archive tasks', async () => {
      const mockResponse = { archived: 2 }
      ;(apiClient.post as jest.Mock).mockResolvedValue(mockResponse)

      const result = await projectsAPI.bulkArchiveTasks('proj-1', [
        'task-1',
        'task-2',
      ])

      expect(apiClient.post).toHaveBeenCalledWith(
        '/projects/proj-1/tasks/bulk-archive',
        {
          task_ids: ['task-1', 'task-2'],
        }
      )
      expect(result).toEqual(mockResponse)
    })
  })

  describe('bulk operations on projects', () => {
    it('should bulk delete projects', async () => {
      const mockResponse = { deleted: 3 }
      ;(apiClient.post as jest.Mock).mockResolvedValue(mockResponse)

      const result = await projectsAPI.bulkDeleteProjects([
        'proj-1',
        'proj-2',
        'proj-3',
      ])

      expect(apiClient.post).toHaveBeenCalledWith('/projects/bulk-delete', {
        project_ids: ['proj-1', 'proj-2', 'proj-3'],
      })
      expect(result).toEqual(mockResponse)
    })

    it('should bulk archive projects', async () => {
      const mockResponse = { archived: 2 }
      ;(apiClient.post as jest.Mock).mockResolvedValue(mockResponse)

      const result = await projectsAPI.bulkArchiveProjects(['proj-1', 'proj-2'])

      expect(apiClient.post).toHaveBeenCalledWith('/projects/bulk-archive', {
        project_ids: ['proj-1', 'proj-2'],
      })
      expect(result).toEqual(mockResponse)
    })

    it('should bulk unarchive projects', async () => {
      const mockResponse = { unarchived: 2 }
      ;(apiClient.post as jest.Mock).mockResolvedValue(mockResponse)

      const result = await projectsAPI.bulkUnarchiveProjects([
        'proj-1',
        'proj-2',
      ])

      expect(apiClient.post).toHaveBeenCalledWith('/projects/bulk-unarchive', {
        project_ids: ['proj-1', 'proj-2'],
      })
      expect(result).toEqual(mockResponse)
    })

    it('should bulk export projects', async () => {
      const mockBlob = new Blob(['test data'], { type: 'application/json' })
      ;(apiClient.post as jest.Mock).mockResolvedValue(mockBlob)

      const result = await projectsAPI.bulkExportProjects(
        ['proj-1', 'proj-2'],
        'json',
        true
      )

      expect(apiClient.post).toHaveBeenCalledWith('/projects/bulk-export', {
        project_ids: ['proj-1', 'proj-2'],
        format: 'json',
        include_data: true,
      })
      expect(result).toEqual(mockBlob)
    })

    it('should bulk export full projects', async () => {
      const mockBlob = new Blob(['test data'], { type: 'application/zip' })
      ;(apiClient.post as jest.Mock).mockResolvedValue(mockBlob)

      const result = await projectsAPI.bulkExportFullProjects([
        'proj-1',
        'proj-2',
      ])

      expect(apiClient.post).toHaveBeenCalledWith(
        '/projects/bulk-export-full',
        {
          project_ids: ['proj-1', 'proj-2'],
        }
      )
      expect(result).toEqual(mockBlob)
    })
  })

  describe('importProject', () => {
    it('should import project from file', async () => {
      const mockFile = new File(['{}'], 'project.json', {
        type: 'application/json',
      })
      const mockResponse = {
        message: 'Project imported successfully',
        project_id: 'proj-new',
        project_title: 'Imported Project',
        project_url: '/projects/proj-new',
        statistics: { tasks: 10, annotations: 5 },
      }

      ;(apiClient.post as jest.Mock).mockResolvedValue(mockResponse)

      const result = await projectsAPI.importProject(mockFile)

      expect(apiClient.post).toHaveBeenCalledWith(
        '/projects/import-project',
        expect.any(FormData)
      )

      const formData = (apiClient.post as jest.Mock).mock.calls[0][1]
      expect(formData.get('file')).toBe(mockFile)
      expect(result).toEqual(mockResponse)
    })
  })

  describe('member management', () => {
    it('should get project members', async () => {
      const mockMembers = [
        {
          id: 'member-1',
          user_id: 'user-1',
          name: 'User One',
          email: 'user1@example.com',
          role: 'ANNOTATOR',
          is_direct_member: true,
          organization_id: null,
          organization_name: null,
          added_at: '2024-01-01T00:00:00Z',
        },
      ]

      ;(apiClient.get as jest.Mock).mockResolvedValue(mockMembers)

      const result = await projectsAPI.getMembers('proj-1')

      expect(apiClient.get).toHaveBeenCalledWith('/projects/proj-1/members')
      expect(result).toEqual(mockMembers)
    })
  })

  describe('task management', () => {
    it('should update task data', async () => {
      const taskData = { text: 'Updated text', metadata: { key: 'value' } }
      const mockTask: Task = {
        id: 'task-1',
        data: taskData,
        project: 'proj-1',
      } as Task

      ;(apiClient.put as jest.Mock).mockResolvedValue(mockTask)

      const result = await projectsAPI.updateTaskData(
        'proj-1',
        'task-1',
        taskData
      )

      expect(apiClient.put).toHaveBeenCalledWith(
        '/projects/proj-1/tasks/task-1',
        {
          data: taskData,
        }
      )
      expect(result).toEqual(mockTask)
    })

    it('should assign tasks to users', async () => {
      const assignData = {
        task_ids: ['task-1', 'task-2'],
        user_ids: ['user-1', 'user-2'],
      }

      const mockResponse = {
        assignments_created: 4,
        skipped_existing: 0,
        message: 'Tasks assigned successfully',
      }

      ;(apiClient.post as jest.Mock).mockResolvedValue(mockResponse)

      const result = await projectsAPI.assignTasks('proj-1', assignData)

      expect(apiClient.post).toHaveBeenCalledWith(
        '/projects/proj-1/tasks/assign',
        assignData
      )
      expect(result).toEqual(mockResponse)
    })

    it('should recalculate project statistics', async () => {
      const mockResponse = {
        message: 'Statistics recalculated',
        project_id: 'proj-1',
        task_count: 100,
        annotation_count: 50,
        completed_tasks_count: 40,
        progress_percentage: 40.0,
      }

      ;(apiClient.post as jest.Mock).mockResolvedValue(mockResponse)

      const result = await projectsAPI.recalculateStats('proj-1')

      expect(apiClient.post).toHaveBeenCalledWith(
        '/projects/proj-1/recalculate-stats'
      )
      expect(result).toEqual(mockResponse)
    })

    it('should get user assigned tasks', async () => {
      const mockResponse: PaginatedResponse<Task> = {
        items: [{ id: 'task-1', data: { text: 'Task 1' } } as Task],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
      }

      ;(apiClient.get as jest.Mock).mockResolvedValue(mockResponse)

      const result = await projectsAPI.getMyTasks('proj-1')

      expect(apiClient.get).toHaveBeenCalledWith(
        '/projects/proj-1/my-tasks?page=1&page_size=50'
      )
      expect(result).toEqual(mockResponse)
    })

    it('should get user assigned tasks with status filter', async () => {
      const mockResponse: PaginatedResponse<Task> = {
        items: [],
        total: 0,
        page: 1,
        page_size: 50,
        total_pages: 0,
      }

      ;(apiClient.get as jest.Mock).mockResolvedValue(mockResponse)

      await projectsAPI.getMyTasks('proj-1', 1, 50, 'completed')

      expect(apiClient.get).toHaveBeenCalledWith(
        '/projects/proj-1/my-tasks?page=1&page_size=50&status=completed'
      )
    })

    it('should remove task assignment', async () => {
      ;(apiClient.delete as jest.Mock).mockResolvedValue(undefined)

      await projectsAPI.removeTaskAssignment('proj-1', 'task-1', 'assignment-1')

      expect(apiClient.delete).toHaveBeenCalledWith(
        '/projects/proj-1/tasks/task-1/assignments/assignment-1'
      )
    })
  })

  describe('error handling', () => {
    it('should handle network errors', async () => {
      ;(apiClient.get as jest.Mock).mockRejectedValue(
        new Error('Network error')
      )

      await expect(projectsAPI.list()).rejects.toThrow('Network error')
    })

    it('should handle API errors', async () => {
      ;(apiClient.post as jest.Mock).mockRejectedValue(
        new Error('HTTP error! status: 400')
      )

      await expect(projectsAPI.create({ title: 'Test' })).rejects.toThrow(
        'HTTP error! status: 400'
      )
    })

    it('should handle unauthorized errors', async () => {
      ;(apiClient.delete as jest.Mock).mockRejectedValue(
        new Error('HTTP error! status: 403')
      )

      await expect(projectsAPI.delete('proj-1')).rejects.toThrow(
        'HTTP error! status: 403'
      )
    })
  })

  describe('async export jobs', () => {
    it('createExportJob posts to the exports endpoint with the format', async () => {
      ;(apiClient.post as jest.Mock).mockResolvedValue({
        job_id: 'job-1',
        status: 'pending',
      })

      const res = await projectsAPI.createExportJob('proj-1', 'csv')

      expect(apiClient.post).toHaveBeenCalledWith(
        '/projects/proj-1/exports?format=csv'
      )
      expect(res).toEqual({ job_id: 'job-1', status: 'pending' })
    })

    it('createExportJob defaults to the json format', async () => {
      ;(apiClient.post as jest.Mock).mockResolvedValue({
        job_id: 'job-1',
        status: 'pending',
      })

      await projectsAPI.createExportJob('proj-1')

      expect(apiClient.post).toHaveBeenCalledWith(
        '/projects/proj-1/exports?format=json'
      )
    })

    it('getExportJob polls the status endpoint', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue({
        job_id: 'job-1',
        status: 'running',
      })

      const res = await projectsAPI.getExportJob('proj-1', 'job-1')

      expect(apiClient.get).toHaveBeenCalledWith(
        '/projects/proj-1/exports/job-1'
      )
      expect(res.status).toBe('running')
    })

    it('getExportDownloadUrl requests the presigned URL in json mode', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue({
        url: 'https://storage/presigned',
        expires_in: 300,
      })

      const res = await projectsAPI.getExportDownloadUrl('proj-1', 'job-1')

      expect(apiClient.get).toHaveBeenCalledWith(
        '/projects/proj-1/exports/job-1/download?json=1'
      )
      expect(res).toEqual({ url: 'https://storage/presigned', expires_in: 300 })
    })

    it('runProjectExportJob enqueues, polls to completion, and triggers a download', async () => {
      ;(apiClient.post as jest.Mock).mockResolvedValue({
        job_id: 'job-9',
        status: 'pending',
      })

      const statuses = [
        { job_id: 'job-9', project_id: 'proj-1', status: 'pending', progress: 0 },
        { job_id: 'job-9', project_id: 'proj-1', status: 'running', progress: 50 },
        {
          job_id: 'job-9',
          project_id: 'proj-1',
          status: 'completed',
          progress: 100,
        },
      ]
      let pollCount = 0
      ;(apiClient.get as jest.Mock).mockImplementation((url: string) => {
        if (url.endsWith('/download?json=1')) {
          return Promise.resolve({
            url: 'https://storage/presigned',
            expires_in: 300,
          })
        }
        return Promise.resolve(
          statuses[Math.min(pollCount++, statuses.length - 1)]
        )
      })

      const clickSpy = jest.fn()
      const link = { href: '', download: '', click: clickSpy } as any
      const createSpy = jest
        .spyOn(document, 'createElement')
        .mockReturnValue(link)
      const appendSpy = jest
        .spyOn(document.body, 'appendChild')
        .mockImplementation((node) => node as any)
      const removeSpy = jest
        .spyOn(document.body, 'removeChild')
        .mockImplementation((node) => node as any)

      const onStatus = jest.fn()
      await projectsAPI.runProjectExportJob(
        'proj-1',
        'json',
        { onStatus },
        { pollIntervalMs: 1 }
      )

      expect(apiClient.post).toHaveBeenCalledWith(
        '/projects/proj-1/exports?format=json'
      )
      // pending → running → completed: three status callbacks.
      expect(onStatus).toHaveBeenCalledTimes(3)
      // The presigned URL drives a direct browser download (bypasses JS heap).
      expect(link.href).toBe('https://storage/presigned')
      expect(clickSpy).toHaveBeenCalledTimes(1)

      createSpy.mockRestore()
      appendSpy.mockRestore()
      removeSpy.mockRestore()
    })

    it('runProjectExportJob throws the worker error message when the job fails', async () => {
      ;(apiClient.post as jest.Mock).mockResolvedValue({
        job_id: 'job-x',
        status: 'pending',
      })
      ;(apiClient.get as jest.Mock).mockResolvedValue({
        job_id: 'job-x',
        project_id: 'proj-1',
        status: 'failed',
        progress: 0,
        error_message: 'boom in worker',
      })

      await expect(
        projectsAPI.runProjectExportJob('proj-1', 'json', undefined, {
          pollIntervalMs: 1,
        })
      ).rejects.toThrow('boom in worker')
    })

    it('runProjectExportJob aborts polling when the signal is already aborted', async () => {
      ;(apiClient.post as jest.Mock).mockResolvedValue({
        job_id: 'job-a',
        status: 'pending',
      })
      const controller = new AbortController()
      controller.abort()

      await expect(
        projectsAPI.runProjectExportJob('proj-1', 'json', undefined, {
          signal: controller.signal,
        })
      ).rejects.toThrow(/abort/i)
    })
  })
})
